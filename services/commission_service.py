import datetime
from decimal import Decimal
from sqlalchemy.orm import Session
from currency_utils import D, DECIMAL_ZERO
from models import CommissionPolicy, CommissionEntry, Reservation, TreasuryTransaction


class CommissionAlreadyPaidError(ValueError):
    pass


_ROLE_RECIPIENT_MAP = {
    "reservation_rep": ("employee_id", "employee"),
    "travel_agent": ("travel_agent_id", "agent"),
    "sales_rep": ("sales_rep_id", "employee"),
    "marketing_rep": ("marketing_rep_id", "employee"),
    "ops_supplier": ("ops_supplier_id", "supplier"),
}


_ROLE_LEGACY_FIELD = {
    "reservation_rep": "employee_commission",
    "travel_agent": "travel_agent_commission_amount",
    "sales_rep": "sales_rep_commission_amount",
    "marketing_rep": "marketing_rep_commission_amount",
    "ops_supplier": "ops_supplier_commission_amount",
}


class CommissionService:
    def __init__(self, db: Session):
        self.db = db

    def apply_policies(self, reservation: Reservation):
        self.db.query(CommissionEntry).filter(
            CommissionEntry.reservation_id == reservation.id
        ).delete()

        # 1) العمولات اليدوية القديمة (لسه شغالة ومترحّلة تلقائيًا للدفتر
        #    عند تأكيد الحجز عن طريق post_commission) — بنسجّلها هنا كمان
        #    كـ CommissionEntry بحالة "accrued" عشان تظهر وتُدار من نفس
        #    الشاشة والمسار زي أي عمولة تانية، من غير ما نكرر القيد
        #    المحاسبي بتاعها (already booked = accrued=1).
        for role, legacy_field in _ROLE_LEGACY_FIELD.items():
            amt = D(getattr(reservation, legacy_field, 0))
            if amt <= DECIMAL_ZERO:
                continue
            role_key, rtype = _ROLE_RECIPIENT_MAP.get(role, (None, None))
            recipient_id = getattr(reservation, role_key, None) if role_key else None
            if not recipient_id:
                continue
            self.db.add(CommissionEntry(
                reservation_id=reservation.id, recipient_id=recipient_id, recipient_type=rtype,
                role=role, status="accrued", base_amount=amt, calculated_amount=amt,
                accrued=1, source="legacy", earned_date=datetime.datetime.utcnow(),
            ))

        # 2) محرك السياسات — بيتخطى أي دور اتغطى بالفعل بمبلغ يدوي (فوق)
        #    عشان يتفادى حساب نفس العمولة مرتين.
        policies = self.db.query(CommissionPolicy).filter(CommissionPolicy.is_active == 1).all()
        for policy in policies:
            match = self._policy_matches_reservation(policy, reservation)
            if not match:
                continue
            recipient_id, rtype = match
            legacy_field = _ROLE_LEGACY_FIELD.get(policy.role)
            if legacy_field and D(getattr(reservation, legacy_field, 0)) > DECIMAL_ZERO:
                continue
            base_amt = self._policy_base_amount(policy, reservation)
            comm_amt = Reservation.compute_commission(policy.rate_type, policy.rate_value, base_amt)
            if policy.min_amount > DECIMAL_ZERO and comm_amt < policy.min_amount:
                comm_amt = policy.min_amount
            if policy.max_amount > DECIMAL_ZERO and comm_amt > policy.max_amount:
                comm_amt = policy.max_amount
            entry = CommissionEntry(
                policy_id=policy.id,
                reservation_id=reservation.id,
                recipient_id=recipient_id,
                recipient_type=rtype,
                role=policy.role,
                status="calculated",
                base_amount=base_amt,
                calculated_amount=comm_amt,
                accrued=0, source="policy",
            )
            self.db.add(entry)

    def _policy_base_amount(self, policy: CommissionPolicy, reservation: Reservation) -> Decimal:
        if policy.commission_base == "sale_price":
            return reservation.net_sale_price
        if policy.commission_base == "net_profit":
            return reservation.net_profit
        if policy.commission_base == "collected_amount":
            total_collected = DECIMAL_ZERO
            for alloc in reservation.collection_allocations:
                total_collected += D(alloc.amount or 0)
            return total_collected
        return reservation.total_profit

    def _policy_matches_reservation(self, policy: CommissionPolicy, reservation: Reservation):
        if not policy.is_active:
            return None
        role_key, rtype = _ROLE_RECIPIENT_MAP.get(policy.role, (None, None))
        if not role_key:
            return None
        recipient_id = getattr(reservation, role_key, None)
        if not recipient_id:
            return None
        import datetime
        today = datetime.date.today()
        rdate = reservation.created_date
        if isinstance(rdate, datetime.datetime):
            rdate = rdate.date()
        elif rdate is None:
            rdate = today
        if policy.valid_from and policy.valid_from > rdate:
            return None
        if policy.valid_until and policy.valid_until < rdate:
            return None
        if policy.applies_to:
            svc_names = {s.name for s in reservation.services}
            allowed = {x.strip() for x in policy.applies_to.split(",")}
            if not svc_names.intersection(allowed):
                return None
        return (recipient_id, rtype)

    def update_entry_status(self, entry_id: int, status: str):
        """تحديث حالة غير مالية فقط (earned / reversed). ممنوع استخدامها لتسجيل الدفع —
        استخدم pay_entry/pay_entries عشان أي تحويل فعلي من الخزنة يتسجل بقيد محاسبي مربوط."""
        if status == "paid":
            raise ValueError("استخدم pay_entry لتسجيل الدفع الفعلي (بيحتاج حساب خزنة لعمل القيد المحاسبي)")
        entry = self.db.query(CommissionEntry).get(entry_id)
        if not entry:
            raise ValueError(f"CommissionEntry {entry_id} not found")
        entry.status = status
        if status == "earned":
            entry.earned_date = datetime.datetime.utcnow()
        elif status == "reversed":
            entry.reversed_date = datetime.datetime.utcnow()
        self.db.flush()

    def pay_entry(self, entry_id: int, account_id: int, created_by: str):
        """دفع عمولة واحدة: يعمل حركة خزنة + قيد محاسبي (مدين عمولات / دائن خزنة)
        ويربط الاثنين بسجل العمولة (linked_txn_id) — يشتغل لأي نوع مستفيد
        (موظف/وكيل/مورد) بنفس المسار، عكس النظام القديم اللي كان بيدفع الموظفين
        بس عن طريق الرواتب ويسيب عمولات الوكلاء والموردين معلّقة للأبد."""
        return self.pay_entries([entry_id], account_id, created_by)[0]

    def pay_entries(self, entry_ids: list, account_id: int, created_by: str):
        """دفع عدة عمولات دفعة واحدة بحركة خزنة وقيد محاسبي واحد (زي كشف عمولات شهري).
        العمولات المتراكمة مسبقًا (accrued=1، من الحقول اليدوية القديمة) بتتسوى
        كذمة دائنة قائمة (Dr AP)، والعمولات اللي لسه معملهاش قيد (accrued=0،
        من محرك السياسات) بتتسجل كمصروف جديد وقت الدفع (Dr Commission Expense)
        — عشان مفيش عمولة تتحسب مرتين في قائمة الدخل."""
        from services.treasury_service import TreasuryService
        from services.accounting_service import AccountingService

        entries = self.db.query(CommissionEntry).filter(CommissionEntry.id.in_(entry_ids)).all()
        if not entries:
            raise ValueError("لا توجد عمولات مطابقة")
        for e in entries:
            if e.status == "paid":
                raise CommissionAlreadyPaidError(f"العمولة #{e.id} مدفوعة بالفعل")

        total = sum((D(e.calculated_amount) for e in entries), DECIMAL_ZERO)
        if total <= DECIMAL_ZERO:
            raise ValueError("قيمة العمولات صفر — لا يوجد ما يُدفع")

        accrued_total = sum((D(e.calculated_amount) for e in entries if e.accrued), DECIMAL_ZERO)
        new_expense_total = total - accrued_total

        ts = TreasuryService(self.db)
        ts.validate_withdrawal(account_id, total, "دفع عمولات")

        names = ", ".join(f"#{e.id}" for e in entries[:5]) + (" ..." if len(entries) > 5 else "")
        txn = TreasuryTransaction(
            account_id=account_id, type="out", amount=total,
            description=f"دفع عمولات ({names})",
            date=datetime.date.today(),
        )
        self.db.add(txn)
        self.db.flush()
        ts.deduct_balance(account_id, total)

        acc = AccountingService(self.db)
        lines = []
        if accrued_total > DECIMAL_ZERO:
            lines.append((acc._acc_id("ap"), accrued_total, DECIMAL_ZERO))
        if new_expense_total > DECIMAL_ZERO:
            lines.append((acc._acc_id("commissions"), new_expense_total, DECIMAL_ZERO))
        lines.append((acc._acc_id("treasury"), DECIMAL_ZERO, total))
        acc.post(
            lines=lines,
            source_type="commission_payment", source_id=txn.id,
            description=f"دفع عمولات: {names}",
            created_by=created_by,
            treasury_account_id=account_id,
        )

        now = datetime.datetime.utcnow()
        for e in entries:
            e.status = "paid"
            e.paid_date = now
            e.paid_amount = D(e.calculated_amount)
            e.linked_txn_id = txn.id
        self.db.flush()
        return entries
