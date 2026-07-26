"""
LedgerService: the single gateway through which EVERY financial event in
the system posts a balanced journal entry. Reservation, Collection,
SupplierPayment, Expense, Withdrawal services all call into this — they
never touch JournalEntry/JournalLine directly. This guarantees:
  1. Every entry is balanced (enforced here, structurally).
  2. There is one, and only one, code path that can create financial history.
  3. Account.get_balance() below is computed FROM these entries — never stored.
"""
from typing import List, Tuple
from datetime import date
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.models.accounting import Account, JournalEntry, JournalLine
from app.core.exceptions import JournalImbalanceError


class LedgerService:
    def __init__(self, db: Session):
        self.db = db

    def _next_entry_number(self) -> str:
        year = date.today().year
        count = self.db.query(JournalEntry).count() + 1
        return f"JE-{year}-{count:05d}"

    def post(
        self,
        lines: List[Tuple[int, float, float]],   # (account_id, debit, credit)
        source_type: str,
        source_id: int = None,
        description: str = "",
        created_by: str = "system",
        entry_date: date = None,
    ) -> JournalEntry:
        total_debit = sum(d for _, d, _ in lines)
        total_credit = sum(c for _, _, c in lines)
        if abs(total_debit - total_credit) > 0.01:
            raise JournalImbalanceError(
                f"Unbalanced entry: debit={total_debit:.2f} credit={total_credit:.2f} "
                f"(source={source_type}#{source_id})"
            )

        entry = JournalEntry(
            entry_number=self._next_entry_number(),
            date=entry_date or date.today(),
            source_type=source_type, source_id=source_id,
            description=description, created_by=created_by,
        )
        self.db.add(entry)
        self.db.flush()

        for account_id, debit, credit in lines:
            self.db.add(JournalLine(entry_id=entry.id, account_id=account_id, debit=debit, credit=credit))

        self.db.flush()
        return entry

    def get_balance(self, account_id: int, as_of: date = None) -> float:
        """Derived balance = sum(debit) - sum(credit), sign-adjusted by normal_side."""
        account = self.db.get(Account, account_id)
        q = self.db.query(
            func.coalesce(func.sum(JournalLine.debit), 0),
            func.coalesce(func.sum(JournalLine.credit), 0),
        ).join(JournalEntry).filter(JournalLine.account_id == account_id)
        if as_of:
            q = q.filter(JournalEntry.date <= as_of)
        debit, credit = q.first()
        raw = debit - credit
        return raw if account.normal_side == "debit" else -raw

    # ---------------- Pre-built posting recipes for existing modules ----------------
    def post_reservation_sale(self, accounts: dict, reservation, created_by: str):
        """Dr Accounts Receivable / Cr Sales Revenue — recognizes the sale."""
        self.post(
            lines=[
                (accounts["accounts_receivable"], reservation.company_cost, 0),
                (accounts["sales_revenue"], 0, reservation.company_cost),
            ],
            source_type="reservation", source_id=reservation.id,
            description=f"Sale recognized — booking {reservation.booking_number}",
            created_by=created_by,
        )
        """Dr Cost of Sales / Cr Accounts Payable — recognizes the cost."""
        self.post(
            lines=[
                (accounts["cost_of_sales"], reservation.stay_cost, 0),
                (accounts["accounts_payable"], 0, reservation.stay_cost),
            ],
            source_type="reservation", source_id=reservation.id,
            description=f"Cost recognized — booking {reservation.booking_number}",
            created_by=created_by,
        )

    def post_collection(self, accounts: dict, amount: float, source_id: int, created_by: str):
        """Dr Cash/Treasury / Cr Accounts Receivable."""
        self.post(
            lines=[(accounts["treasury"], amount, 0), (accounts["accounts_receivable"], 0, amount)],
            source_type="collection", source_id=source_id,
            description="Customer collection", created_by=created_by,
        )

    def post_supplier_payment(self, accounts: dict, amount: float, source_id: int, created_by: str):
        """Dr Accounts Payable / Cr Cash/Treasury."""
        self.post(
            lines=[(accounts["accounts_payable"], amount, 0), (accounts["treasury"], 0, amount)],
            source_type="supplier_payment", source_id=source_id,
            description="Supplier payment", created_by=created_by,
        )
