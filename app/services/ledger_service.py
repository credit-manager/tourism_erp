"""
LedgerService: the single gateway for financial journal posting.

All financial events should be posted through this service. The service
validates balanced double-entry lines, rejects invalid debit/credit lines,
prevents duplicate source postings, and supports explicit reversals.
"""
from typing import List, Tuple, Optional
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.models.accounting import Account, JournalEntry, JournalLine
from app.core.exceptions import JournalImbalanceError

_CENT = Decimal("0.01")
_ZERO = Decimal("0.00")
_TOLERANCE = Decimal("0.01")


def _money(value) -> Decimal:
    """Normalize monetary input without introducing binary float errors."""
    return Decimal(str(value or 0)).quantize(_CENT, rounding=ROUND_HALF_UP)


class LedgerService:
    def __init__(self, db: Session):
        self.db = db

    def _next_entry_number(self) -> str:
        """Return the next human-readable number.

        The database unique constraint on JournalEntry.entry_number remains the
        final guard against collisions. Deployments with high write concurrency
        should use a DB sequence/numbering table in a follow-up migration.
        """
        year = date.today().year
        prefix = f"JE-{year}-"
        last_number = (
            self.db.query(func.max(JournalEntry.entry_number))
            .filter(JournalEntry.entry_number.like(f"{prefix}%"))
            .scalar()
        )
        if not last_number:
            next_no = 1
        else:
            try:
                next_no = int(last_number.rsplit("-", 1)[1]) + 1
            except (ValueError, IndexError):
                next_no = 1
        return f"{prefix}{next_no:05d}"

    def _existing_source_entry(self, source_type: str, source_id: Optional[int]):
        if source_id is None:
            return None
        return (
            self.db.query(JournalEntry)
            .filter(
                JournalEntry.source_type == source_type,
                JournalEntry.source_id == source_id,
                JournalEntry.is_reversal == 0,
            )
            .first()
        )

    def post(
        self,
        lines: List[Tuple[int, float, float]],
        source_type: str,
        source_id: int = None,
        description: str = "",
        created_by: str = "system",
        entry_date: date = None,
        *,
        allow_duplicate_source: bool = False,
    ) -> JournalEntry:
        """Create one balanced journal entry.

        The caller owns the surrounding transaction. If posting raises, the
        caller must rollback the transaction so the operational record and its
        financial history cannot diverge.
        """
        if not lines:
            raise JournalImbalanceError("Cannot post an empty journal entry")

        normalized = []
        total_debit = _ZERO
        total_credit = _ZERO
        for account_id, debit, credit in lines:
            if not account_id:
                raise JournalImbalanceError("Every journal line requires an account_id")
            d = _money(debit)
            c = _money(credit)
            if d < _ZERO or c < _ZERO:
                raise JournalImbalanceError("Debit and credit amounts cannot be negative")
            if d > _ZERO and c > _ZERO:
                raise JournalImbalanceError("A journal line cannot contain both debit and credit")
            if d == _ZERO and c == _ZERO:
                raise JournalImbalanceError("A journal line cannot have zero debit and credit")
            normalized.append((account_id, d, c))
            total_debit += d
            total_credit += c

        if abs(total_debit - total_credit) >= _TOLERANCE:
            raise JournalImbalanceError(
                f"Unbalanced entry: debit={total_debit:.2f} credit={total_credit:.2f} "
                f"(source={source_type}#{source_id})"
            )

        if not allow_duplicate_source:
            existing = self._existing_source_entry(source_type, source_id)
            if existing:
                raise JournalImbalanceError(
                    f"Duplicate financial posting for {source_type}#{source_id}; "
                    f"existing entry={existing.entry_number}"
                )

        entry = JournalEntry(
            entry_number=self._next_entry_number(),
            date=entry_date or date.today(),
            source_type=source_type,
            source_id=source_id,
            description=description,
            created_by=created_by,
        )
        self.db.add(entry)
        self.db.flush()

        for account_id, debit, credit in normalized:
            self.db.add(
                JournalLine(
                    entry_id=entry.id,
                    account_id=account_id,
                    debit=d,
                    credit=c,
                )
            )

        self.db.flush()
        return entry

    def reverse_entry(
        self,
        entry_id: int,
        created_by: str,
        reason: str,
        entry_date: date = None,
    ) -> JournalEntry:
        """Create a balanced reversal without deleting accounting history."""
        entry = self.db.get(JournalEntry, entry_id)
        if not entry:
            raise ValueError(f"Journal entry {entry_id} not found")
        if entry.is_reversal:
            raise ValueError("A reversal entry cannot itself be reversed")
        if entry.reversals:
            raise ValueError(f"Journal entry {entry.entry_number} is already reversed")
        if not entry.lines:
            raise JournalImbalanceError("Cannot reverse an entry with no lines")

        reversal = JournalEntry(
            entry_number=self._next_entry_number(),
            date=entry_date or date.today(),
            source_type="reversal",
            source_id=entry.id,
            description=f"Reversal of {entry.entry_number}: {reason}",
            created_by=created_by,
            reversed_entry_id=entry.id,
            is_reversal=1,
        )
        self.db.add(reversal)
        self.db.flush()

        for line in entry.lines:
            self.db.add(
                JournalLine(
                    entry_id=reversal.id,
                    account_id=line.account_id,
                    debit=_money(line.credit),
                    credit=_money(line.debit),
                    currency_id=line.currency_id,
                    exchange_rate=line.exchange_rate,
                    amount_in_base_currency=line.amount_in_base_currency,
                    cost_center=line.cost_center,
                    branch=line.branch,
                    customer_id=line.customer_id,
                    supplier_id=line.supplier_id,
                    reservation_id=line.reservation_id,
                    memo=f"Reversal of line {line.id}",
                )
            )
        self.db.flush()
        return reversal

    def get_balance(self, account_id: int, as_of: date = None) -> float:
        """Derived balance = sum(debit) - sum(credit), sign-adjusted by normal_side."""
        account = self.db.get(Account, account_id)
        if not account:
            raise ValueError(f"Account {account_id} not found")
        q = self.db.query(
            func.coalesce(func.sum(JournalLine.debit), 0),
            func.coalesce(func.sum(JournalLine.credit), 0),
        ).join(JournalEntry).filter(JournalLine.account_id == account_id)
        if as_of:
            q = q.filter(JournalEntry.date <= as_of)
        debit, credit = q.first()
        raw = Decimal(str(debit or 0)) - Decimal(str(credit or 0))
        return float(raw if account.normal_side == "debit" else -raw)

    def post_reservation_sale(self, accounts: dict, reservation, created_by: str):
        """Recognize the configured reservation sale and hotel cost."""
        sale_amount = getattr(reservation, "company_cost", None)
        hotel_cost = getattr(reservation, "stay_cost", None)
        if sale_amount is None or _money(sale_amount) <= _ZERO:
            raise ValueError("Reservation sale amount must be greater than zero")
        self.post(
            lines=[
                (accounts["accounts_receivable"], sale_amount, 0),
                (accounts["sales_revenue"], 0, sale_amount),
            ],
            source_type="reservation_sale", source_id=reservation.id,
            description=f"Sale recognized — booking {reservation.booking_number}",
            created_by=created_by,
        )
        if hotel_cost is not None and _money(hotel_cost) > _ZERO:
            self.post(
                lines=[
                    (accounts["cost_of_sales"], hotel_cost, 0),
                    (accounts["accounts_payable"], 0, hotel_cost),
                ],
                source_type="reservation_cost", source_id=reservation.id,
                description=f"Cost recognized — booking {reservation.booking_number}",
                created_by=created_by,
            )

    def post_collection(self, accounts: dict, amount: float, source_id: int, created_by: str):
        """Dr Cash/Treasury / Cr Accounts Receivable."""
        amount = _money(amount)
        if amount <= _ZERO:
            raise ValueError("Collection amount must be greater than zero")
        self.post(
            lines=[
                (accounts["treasury"], amount, 0),
                (accounts["accounts_receivable"], 0, amount),
            ],
            source_type="collection", source_id=source_id,
            description="Customer collection", created_by=created_by,
        )

    def post_supplier_payment(self, accounts: dict, amount: float, source_id: int, created_by: str):
        """Dr Accounts Payable / Cr Cash/Treasury."""
        amount = _money(amount)
        if amount <= _ZERO:
            raise ValueError("Supplier payment amount must be greater than zero")
        self.post(
            lines=[
                (accounts["accounts_payable"], amount, 0),
                (accounts["treasury"], 0, amount),
            ],
            source_type="supplier_payment", source_id=source_id,
            description="Supplier payment", created_by=created_by,
        )
