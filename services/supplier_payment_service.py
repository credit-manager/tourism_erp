import datetime
from decimal import Decimal
from sqlalchemy.orm import Session
from currency_utils import D, DECIMAL_ZERO
from models import (
    SupplierPayment, SupplierPaymentAllocation, Reservation, TreasuryTransaction,
    generate_supplier_payment_number,
)
from services.reconciliation_service import ReconciliationService


class SupplierPaymentService:
    def __init__(self, db: Session, user):
        self.db = db
        self.user = user

    def create(self, form_data: dict) -> SupplierPayment:
        supplier_id = int(form_data.get("supplier_id"))
        total_amount = D(form_data.get("total_amount"))
        notes = form_data.get("notes", "")
        reservation_ids = [int(x) for x in form_data.get("reservation_ids", [])]
        account_id = form_data.get("account_id")
        account_id = int(account_id) if account_id and str(account_id).strip() else None
        currency_id = form_data.get("currency_id")
        currency_id = int(currency_id) if currency_id and str(currency_id).strip() else None
        exchange_rate_val = D(form_data.get("exchange_rate", 1))
        amount_currency = D(form_data.get("amount_currency", total_amount))
        amount_base = amount_currency * exchange_rate_val if exchange_rate_val > 0 else total_amount

        payment = SupplierPayment(
            payment_number=generate_supplier_payment_number(self.db), date=datetime.date.today(),
            supplier_id=supplier_id, total_amount=total_amount, allocated_amount=DECIMAL_ZERO,
            unallocated_amount=total_amount, notes=notes, account_id=account_id,
            currency_id=currency_id, amount_currency=amount_currency, amount_base=amount_base,
            exchange_rate=exchange_rate_val,
            status="draft", created_by=self.user.username,
        )
        self.db.add(payment)
        self.db.flush()
        self._allocate(payment, reservation_ids, total_amount)
        return payment

    def _allocate(self, payment, reservation_ids, amount):
        remaining = D(amount)
        affected = []
        for rid in reservation_ids:
            if remaining <= DECIMAL_ZERO: break
            r = self.db.query(Reservation).get(rid)
            if not r: continue
            owed = r.remaining_to_hotel
            if owed <= DECIMAL_ZERO: continue
            applied = min(owed, remaining)
            self.db.add(SupplierPaymentAllocation(
                payment_id=payment.id, reservation_id=r.id,
                amount=applied, date=datetime.date.today()
            ))
            payment.allocated_amount = D(payment.allocated_amount) + applied
            remaining -= applied
            affected.append(r)
        payment.unallocated_amount = remaining
        for r in affected:
            ReconciliationService.sync_reservation_paid_fields(self.db, r)

    def allocate_remaining(self, payment_id: int, reservation_ids: list, amount: Decimal = None):
        payment = self.db.query(SupplierPayment).get(payment_id)
        if not payment:
            raise ValueError(f"SupplierPayment {payment_id} not found")
        if amount is None:
            amount = D(payment.unallocated_amount)
        amount = min(amount, D(payment.unallocated_amount))
        remaining_before = D(payment.unallocated_amount)
        payment.unallocated_amount = remaining_before - amount
        remaining = amount
        for rid in reservation_ids:
            if remaining <= DECIMAL_ZERO: break
            r = self.db.query(Reservation).get(rid)
            if not r: continue
            owed = D(r.remaining_to_hotel)
            if owed <= DECIMAL_ZERO: continue
            applied = min(owed, remaining)
            self.db.add(SupplierPaymentAllocation(
                payment_id=payment.id, reservation_id=r.id,
                amount=applied, date=datetime.date.today()
            ))
            payment.allocated_amount = D(payment.allocated_amount) + applied
            remaining -= applied
        payment.unallocated_amount = D(payment.unallocated_amount) + remaining
        for rid in reservation_ids:
            r = self.db.query(Reservation).get(rid)
            if r: ReconciliationService.sync_reservation_paid_fields(self.db, r)
        if payment.status == "posted":
            from services.accounting_service import AccountingService
            acc = AccountingService(self.db)
            if amount > DECIMAL_ZERO:
                acc.post(
                    lines=[(acc._acc_id("ap"), amount, DECIMAL_ZERO),
                           (acc._acc_id("suspense"), DECIMAL_ZERO, amount)],
                    source_type="supplier_payment", source_id=payment_id,
                    description=f"توزيع دفعة مورد على حجوزات ({payment.payment_number})",
                    created_by=self.user.username,
                    supplier_id=payment.supplier_id,
                )
        self.db.flush()

    def post(self, payment_id: int):
        payment = self.db.query(SupplierPayment).get(payment_id)
        if not payment:
            raise ValueError(f"SupplierPayment {payment_id} not found")
        from services.treasury_service import TreasuryService, InsufficientBalanceError, AccountNotSelectedError
        svc = TreasuryService(self.db)
        try:
            account = svc.resolve_account(payment.account_id, "supplier_payment")
            if not account:
                raise AccountNotSelectedError("لم يتم اختيار حساب للدفع")
            svc.validate_withdrawal(account.id, D(payment.total_amount),
                f"دفعة {payment.payment_number} لمورد {payment.supplier.name if payment.supplier else ''}")
        except (InsufficientBalanceError, AccountNotSelectedError):
            raise
        from services.workflow_service import WorkflowService
        WorkflowService(self.db).post(payment, self.user)
        if not payment.account_id:
            payment.account_id = account.id
        self.db.add(TreasuryTransaction(
            account_id=account.id, type="out", amount=D(payment.total_amount),
            description=f"دفعة {payment.payment_number} لمورد {payment.supplier.name if payment.supplier else ''}",
            date=datetime.date.today()
        ))
        svc.deduct_balance(account.id, D(payment.total_amount))
        from services.accounting_service import AccountingService
        acc = AccountingService(self.db)
        acc.post_supplier_payment(payment, D(payment.total_amount), created_by=self.user.username)
        self.db.flush()
