import datetime
from decimal import Decimal
from sqlalchemy.orm import Session
from currency_utils import D, DECIMAL_ZERO
from models import (
    Reservation, Collection, CollectionAllocation, TreasuryTransaction,
    generate_collection_number,
)
from services.reconciliation_service import ReconciliationService


class CollectionService:
    def __init__(self, db: Session, user):
        self.db = db
        self.user = user

    def create(self, form_data: dict) -> Collection:
        payer_name = (form_data.get("payer_name") or "").strip()
        total_amount = D(form_data.get("total_amount"))
        notes = (form_data.get("notes") or "").strip()
        payment_method = form_data.get("payment_method", "cash")
        allocation_mode = form_data.get("allocation_mode", "auto")
        customer_id = form_data.get("customer_id")
        customer_id = int(customer_id) if customer_id and str(customer_id).strip() else None
        reservation_ids = form_data.get("reservation_ids", [])
        account_id = form_data.get("account_id")
        account_id = int(account_id) if account_id and str(account_id).strip() else None
        currency_id = form_data.get("currency_id")
        currency_id = int(currency_id) if currency_id and str(currency_id).strip() else None
        exchange_rate_val = D(form_data.get("exchange_rate", 1))
        amount_currency = D(form_data.get("amount_currency", total_amount))
        amount_base = amount_currency * exchange_rate_val if exchange_rate_val > 0 else total_amount

        collection = Collection(
            collection_number=generate_collection_number(self.db), date=datetime.date.today(),
            customer_id=customer_id, payer_name=payer_name, total_amount=total_amount,
            allocated_amount=DECIMAL_ZERO, unallocated_amount=total_amount, account_id=account_id,
            currency_id=currency_id, amount_currency=amount_currency, amount_base=amount_base,
            exchange_rate=exchange_rate_val,
            notes=f"طريقة الدفع: {payment_method}" + (f" - {notes}" if notes else ""),
            status="draft", created_by=self.user.username,
        )
        self.db.add(collection)
        self.db.flush()

        if allocation_mode == "manual":
            self._allocate_manual(collection, reservation_ids, total_amount, form_data)
        else:
            self._allocate_auto(collection, reservation_ids, total_amount)
        return collection

    def _allocate_manual(self, collection, reservation_ids, total_amount, form_data):
        allocated_total = DECIMAL_ZERO
        for rid in reservation_ids:
            r = self.db.query(Reservation).get(rid)
            if not r: continue
            raw_amount = form_data.get(f"allocation_amount_{rid}") or 0
            requested = D(raw_amount)
            if requested <= DECIMAL_ZERO: continue
            owed = max(D(r.remaining_to_office), DECIMAL_ZERO)
            applied = min(requested, owed, total_amount - allocated_total)
            if applied <= DECIMAL_ZERO: continue
            self.db.add(CollectionAllocation(
                collection_id=collection.id, reservation_id=r.id,
                amount=applied, date=datetime.date.today()
            ))
            allocated_total += applied
            if allocated_total >= total_amount: break
        collection.allocated_amount = allocated_total
        collection.unallocated_amount = max(total_amount - allocated_total, DECIMAL_ZERO)
        for rid in reservation_ids:
            r = self.db.query(Reservation).get(rid)
            if r: ReconciliationService.sync_reservation_paid_fields(self.db, r)

    def _allocate_auto(self, collection, reservation_ids, total_amount):
        remaining = D(total_amount)
        affected = []
        for rid in reservation_ids:
            if remaining <= DECIMAL_ZERO: break
            r = self.db.query(Reservation).get(rid)
            if not r: continue
            owed = r.remaining_to_office
            if owed <= DECIMAL_ZERO: continue
            applied = min(owed, remaining)
            self.db.add(CollectionAllocation(
                collection_id=collection.id, reservation_id=r.id,
                amount=applied, date=datetime.date.today()
            ))
            collection.allocated_amount = D(collection.allocated_amount) + applied
            remaining -= applied
            affected.append(r)
        collection.unallocated_amount = remaining
        for r in affected:
            ReconciliationService.sync_reservation_paid_fields(self.db, r)

    def allocate_remaining(self, collection_id: int, reservation_ids: list, amount: Decimal = None):
        collection = self.db.query(Collection).get(collection_id)
        if not collection:
            raise ValueError(f"Collection {collection_id} not found")
        if amount is None:
            amount = D(collection.unallocated_amount)
        amount = min(amount, D(collection.unallocated_amount))
        available = D(collection.unallocated_amount)
        collection.unallocated_amount = available - amount
        remaining = amount
        for rid in reservation_ids:
            if remaining <= DECIMAL_ZERO: break
            r = self.db.query(Reservation).get(rid)
            if not r: continue
            owed = D(r.remaining_to_office)
            if owed <= DECIMAL_ZERO: continue
            applied = min(owed, remaining)
            self.db.add(CollectionAllocation(
                collection_id=collection.id, reservation_id=r.id,
                amount=applied, date=datetime.date.today()
            ))
            collection.allocated_amount = D(collection.allocated_amount) + applied
            remaining -= applied
        collection.unallocated_amount = D(collection.unallocated_amount) + remaining
        for rid in reservation_ids:
            r = self.db.query(Reservation).get(rid)
            if r: ReconciliationService.sync_reservation_paid_fields(self.db, r)
        if collection.status == "posted":
            from services.accounting_service import AccountingService
            acc = AccountingService(self.db)
            for rid in reservation_ids:
                r = self.db.query(Reservation).get(rid)
                if not r: continue
                ca = self.db.query(CollectionAllocation).filter(
                    CollectionAllocation.collection_id == collection_id,
                    CollectionAllocation.reservation_id == rid,
                ).order_by(CollectionAllocation.id.desc()).first()
                if ca:
                    acc.post_collection_allocation(collection, ca.amount, r,
                                                   created_by=self.user.username)
        self.db.flush()

    def post(self, collection_id: int):
        collection = self.db.query(Collection).get(collection_id)
        if not collection:
            raise ValueError(f"Collection {collection_id} not found")
        from services.workflow_service import WorkflowService
        WorkflowService(self.db).post(collection, self.user)
        tt_amount = D(collection.total_amount)
        if tt_amount > DECIMAL_ZERO:
            from services.treasury_service import TreasuryService, AccountNotSelectedError
            ts = TreasuryService(self.db)
            try:
                account = ts.resolve_account(collection.account_id, "collection")
                if not account:
                    raise AccountNotSelectedError("لم يتم اختيار حساب للتحصيل")
                self.db.add(TreasuryTransaction(
                    account_id=account.id, type="in", amount=tt_amount,
                    description=f"تحصيل {collection.collection_number} - {collection.payer_name}",
                    date=datetime.date.today()
                ))
                ts.add_balance(account.id, tt_amount)
                if not collection.account_id:
                    collection.account_id = account.id
            except AccountNotSelectedError as e:
                raise
        from services.accounting_service import AccountingService
        acc = AccountingService(self.db)
        acc.post_collection(collection, tt_amount, created_by=self.user.username)
        self.db.flush()
