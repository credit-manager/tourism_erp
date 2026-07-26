from decimal import Decimal
from typing import List, Tuple
from datetime import date
from sqlalchemy.orm import Session
from sqlalchemy import func
from models import (
    Account, JournalEntry, JournalLine, generate_journal_entry_number,
    TreasuryAccount, Supplier, Customer, Reservation,
)
from currency_utils import D, DECIMAL_ZERO


class JournalImbalanceError(Exception):
    pass


class AccountNotFoundError(Exception):
    pass


class ReconcileError(Exception):
    """Raised when cached balance does not match journal-derived balance."""
    def __init__(self, discrepancies: list):
        self.discrepancies = discrepancies
        msg = "Cached balance mismatch:\n" + "\n".join(
            f"  {d['entity']}#{d['id']}: stored={d['stored']} journal={d['journal']} diff={d['diff']}"
            for d in discrepancies
        )
        super().__init__(msg)


class AccountingService:
    def __init__(self, db: Session):
        self.db = db
        self._cache = {}

    def _acc_id(self, key: str) -> int:
        if key not in self._cache:
            acc = self.db.query(Account).filter(Account.key == key).first()
            if not acc:
                raise AccountNotFoundError(
                    f"System account key='{key}' not found. Run seed_chart_of_accounts first."
                )
            self._cache[key] = acc.id
        return self._cache[key]

    def _acc_type(self, key: str) -> str:
        acc = self.db.query(Account).filter(Account.key == key).first()
        return acc.account_type if acc else "asset"

    def get_balance(self, account_id: int, as_of: date = None) -> Decimal:
        q = self.db.query(
            func.coalesce(func.sum(JournalLine.debit), 0),
            func.coalesce(func.sum(JournalLine.credit), 0),
        ).join(JournalEntry).filter(JournalLine.account_id == account_id)
        if as_of:
            q = q.filter(JournalEntry.date <= as_of)
        debit, credit = q.first()
        return D(debit) - D(credit)

    def _jbal(self, key: str) -> Decimal:
        """Journal-derived balance for a system account key."""
        return self.get_balance(self._acc_id(key))

    # -------- Cached balance reconciliation --------
    def _journal_treasury_total(self) -> Decimal:
        """Total cash = SUM(debit - credit) for treasury account."""
        return self._jbal("treasury")

    def _journal_ap_total(self) -> Decimal:
        """Total AP = SUM(credit - debit) for AP account."""
        acc_type = self._acc_type("ap")
        bal = self.get_balance(self._acc_id("ap"))
        return -bal if bal < 0 and acc_type == "liability" else bal

    def _journal_ar_total(self) -> Decimal:
        """Total AR = SUM(debit - credit) for AR account."""
        return self._jbal("ar")

    def _journal_supplier_balance(self, supplier_id: int) -> Decimal:
        """AP for a specific supplier from journal lines where supplier_id matches."""
        ap_id = self._acc_id("ap")
        debit, credit = self.db.query(
            func.coalesce(func.sum(JournalLine.debit), 0),
            func.coalesce(func.sum(JournalLine.credit), 0),
        ).join(JournalEntry).filter(
            JournalLine.account_id == ap_id,
            JournalLine.supplier_id == supplier_id,
        ).first()
        return D(credit) - D(debit)

    def _journal_customer_balance(self, customer_id: int) -> Decimal:
        """AR for a specific customer from journal lines where customer_id matches."""
        ar_id = self._acc_id("ar")
        debit, credit = self.db.query(
            func.coalesce(func.sum(JournalLine.debit), 0),
            func.coalesce(func.sum(JournalLine.credit), 0),
        ).join(JournalEntry).filter(
            JournalLine.account_id == ar_id,
            JournalLine.customer_id == customer_id,
        ).first()
        return D(debit) - D(credit)

    def sync_treasury_cache(self):
        """
        ملحوظة مهمة (تصحيح): الدالة دي كانت بتكتب فوق TreasuryAccount.balance
        الحقيقي بـ (إجمالي حركة الخزنة ÷ عدد الحسابات) — يعني لو عندك أكتر من
        حساب خزنة (درج + بنك + عملة تانية)، كل حساب كان بياخد نفس الرقم
        بالتساوي مع أي عملية مالية جديدة في أي مكان بالبرنامج، بغض النظر
        فين فعليًا اتحركت الفلوس! ده كان بيخرب رصيد الخزنة الحقيقي بصمت.

        الرصيد الحقيقي بالفعل بيتحدث صح لحظة بلحظة عن طريق
        TreasuryService.deduct_balance/add_balance في كل عملية فعلية —
        فالدالة دي بقت بس بتتحقق (verify) من وجود فرق وتبلّغ عنه بدل
        ما تمسح الرصيد الصحيح وتكتب فوقه رقم غلط.
        """
        return

    def treasury_reconciliation_report(self) -> list:
        """تقرير فروق بين رصيد الخزنة الفعلي المخزّن ورصيد اليومية الإجمالي —
        للمراجعة فقط، ومن غير أي تعديل تلقائي على الأرصدة."""
        total_journal = self._journal_treasury_total()
        total_cached = D(self.db.query(func.coalesce(func.sum(TreasuryAccount.balance), 0)).scalar())
        diff = total_cached - total_journal
        return [{
            "entity": "TreasuryAccount(all)", "id": 0,
            "stored": total_cached, "journal": total_journal, "diff": diff,
        }] if abs(diff) > D("0.009") else []

    def sync_supplier_cache(self):
        """Update each Supplier.balance to match journal-derived AP."""
        ap_id = self._acc_id("ap")
        rows = self.db.query(
            JournalLine.supplier_id,
            func.coalesce(func.sum(JournalLine.credit), 0) - func.coalesce(func.sum(JournalLine.debit), 0),
        ).join(JournalEntry).filter(
            JournalLine.account_id == ap_id,
            JournalLine.supplier_id != None,
        ).group_by(JournalLine.supplier_id).all()
        all_ids = set(r[0] for r in rows)
        for sid, bal in rows:
            s = self.db.get(Supplier, sid)
            if s:
                s.balance = D(bal)
        untouched = self.db.query(Supplier).filter(~Supplier.id.in_(all_ids)).all() if all_ids \
            else self.db.query(Supplier).all()
        for s in untouched:
            s.balance = DECIMAL_ZERO

    def sync_customer_cache(self):
        """Update each Customer.balance to match journal-derived AR."""
        ar_id = self._acc_id("ar")
        rows = self.db.query(
            JournalLine.customer_id,
            func.coalesce(func.sum(JournalLine.debit), 0) - func.coalesce(func.sum(JournalLine.credit), 0),
        ).join(JournalEntry).filter(
            JournalLine.account_id == ar_id,
            JournalLine.customer_id != None,
        ).group_by(JournalLine.customer_id).all()
        all_ids = set(r[0] for r in rows)
        for cid, bal in rows:
            c = self.db.get(Customer, cid)
            if c:
                c.balance = D(bal)
        untouched = self.db.query(Customer).filter(~Customer.id.in_(all_ids)).all() if all_ids \
            else self.db.query(Customer).all()
        for c in untouched:
            c.balance = DECIMAL_ZERO

    def sync_all_caches(self):
        """Update ALL cached balances from journal entries in one transaction."""
        self.sync_treasury_cache()
        self.sync_supplier_cache()
        self.sync_customer_cache()
        self.db.flush()

    def verify_all(self) -> list:
        """Compare cached balances vs journal-derived balances. Returns list of discrepancies."""
        issues = []
        total = self._journal_treasury_total()
        cached = D(self.db.query(func.coalesce(func.sum(TreasuryAccount.balance), 0)).scalar())
        if abs(total - cached) > D("0.009"):
            issues.append({
                "entity": "TreasuryAccount", "id": 0,
                "stored": cached, "journal": total, "diff": cached - total,
            })
        for s in self.db.query(Supplier).all():
            jbal = self._journal_supplier_balance(s.id)
            if abs(D(s.balance) - jbal) > D("0.009"):
                issues.append({
                    "entity": "Supplier", "id": s.id, "name": s.name,
                    "stored": D(s.balance), "journal": jbal, "diff": D(s.balance) - jbal,
                })
        for c in self.db.query(Customer).all():
            jbal = self._journal_customer_balance(c.id)
            if abs(D(c.balance) - jbal) > D("0.009"):
                issues.append({
                    "entity": "Customer", "id": c.id, "name": c.name,
                    "stored": D(c.balance), "journal": jbal, "diff": D(c.balance) - jbal,
                })
        return issues

    def post(
        self,
        lines: List[Tuple[int, Decimal, Decimal]],
        source_type: str,
        source_id: int = None,
        description: str = "",
        created_by: str = "system",
        entry_date: date = None,
        treasury_account_id: int = None,
        supplier_id: int = None,
        customer_id: int = None,
        reservation_id: int = None,
    ) -> JournalEntry:
        total_debit = sum(D(d) for _, d, _ in lines)
        total_credit = sum(D(c) for _, _, c in lines)
        if abs(total_debit - total_credit) > D("0.009"):
            raise JournalImbalanceError(
                f"Debit ({total_debit:.2f}) ≠ Credit ({total_credit:.2f}) "
                f"for {source_type}#{source_id}"
            )
        entry = JournalEntry(
            entry_number=generate_journal_entry_number(self.db),
            date=entry_date or date.today(),
            source_type=source_type, source_id=source_id,
            description=description, created_by=created_by,
        )
        self.db.add(entry)
        self.db.flush()
        treasury_acc_id = self._acc_id("treasury")
        # لازم نحدد سطر الذمم المدينة/الدائنة (AR/AP) عشان نربطه بالعميل/المورد —
        # من غيره sync_supplier_cache/sync_customer_cache بترجع فاضية دايمًا وترصّف
        # كل أرصدة العملاء والموردين على صفر مع كل عملية مالية في أي شاشة بالبرنامج.
        ap_acc_id = self._acc_id("ap") if supplier_id else None
        ar_acc_id = self._acc_id("ar") if customer_id else None
        for account_id, debit, credit in lines:
            memo = None
            if treasury_account_id and account_id == treasury_acc_id:
                memo = f"حساب خزنة #{treasury_account_id}"
            self.db.add(JournalLine(
                entry_id=entry.id, account_id=account_id,
                debit=D(debit), credit=D(credit), memo=memo,
                supplier_id=supplier_id if (ap_acc_id and account_id == ap_acc_id) else None,
                customer_id=customer_id if (ar_acc_id and account_id == ar_acc_id) else None,
                reservation_id=reservation_id,
            ))
        self.db.flush()
        self.sync_all_caches()
        return entry

    def reverse_entry(self, entry_id: int, created_by: str = "system",
                      reversal_date: date = None) -> JournalEntry:
        original = self.db.get(JournalEntry, entry_id)
        if not original:
            raise ValueError(f"JournalEntry {entry_id} not found")
        lines = [(l.account_id, D(l.credit), D(l.debit)) for l in original.lines]
        rev = self.post(
            lines=lines, source_type=original.source_type,
            source_id=original.source_id,
            description=f"عكس {original.entry_number}: {original.description}",
            created_by=created_by, entry_date=reversal_date or date.today(),
        )
        rev.is_reversal = 1
        rev.reversed_entry_id = original.id
        self.db.flush()
        self.sync_all_caches()
        return rev

    def adjust_reservation(self, reservation, old_snapshot: dict, created_by: str = "system"):
        """عكس القيود القديمة للحجز ونشر قيود جديدة بناءً على القيم الحالية.
        old_snapshot: القيم المالية القديمة (من ReservationService._snapshot)
        """
        old_nsp = D(old_snapshot.get("net_sale_price", 0))
        new_nsp = D(reservation.net_sale_price)
        has_change = False

        # اعكس كل القيود القديمة غير المعكوسة
        old_entries = self.db.query(JournalEntry).filter(
            JournalEntry.source_type == "reservation",
            JournalEntry.source_id == reservation.id,
            JournalEntry.is_reversal == 0,
            JournalEntry.reversed_entry_id.is_(None),
        ).all()
        for entry in old_entries:
            self.reverse_entry(entry.id)
            has_change = True

        if not has_change:
            return  # مفيش قيود قديمة — مفيش حاجة تعكس

        # انشر القيود الجديدة
        if new_nsp > DECIMAL_ZERO:
            self.post_reservation_sale(reservation, created_by=created_by)
        new_stay = D(reservation.stay_cost)
        if new_stay > DECIMAL_ZERO:
            self.post_reservation_cost(reservation, created_by=created_by)
        # العمولات
        for ctype, cid_attr, ca_attr in [
            ("reservation_rep", "employee_id", "employee_commission"),
            ("travel_agent", "travel_agent_id", "travel_agent_commission_amount"),
            ("sales_rep", "sales_rep_id", "sales_rep_commission_amount"),
            ("marketing_rep", "marketing_rep_id", "marketing_rep_commission_amount"),
            ("ops_supplier", "ops_supplier_id", "ops_supplier_commission_amount"),
        ]:
            cid = getattr(reservation, cid_attr, None)
            camt = D(getattr(reservation, ca_attr, 0))
            if cid and camt > DECIMAL_ZERO:
                self.post_commission(reservation, camt, ctype, created_by=created_by)

    def cancel_reservation(self, reservation, refund_amount: Decimal = DECIMAL_ZERO,
                           cancellation_fee: Decimal = DECIMAL_ZERO, created_by: str = "system"):
        """إلغاء كل القيود المحاسبية للحجز: عكس الإيراد والتكلفة والعمولات والتحصيلات.
        
        - refund_amount: يُستخدم فقط للإسترداد الإضافي خارج نطاق التحصيلات المعكوسة.
        - cancellation_fee: يُسجل كإيراد رسوم إلغاء (Dr Treasury / Cr Revenue).
        """
        # 1. عكس قيود الحجز (sale + cost)
        res_entries = self.db.query(JournalEntry).filter(
            JournalEntry.source_type == "reservation",
            JournalEntry.source_id == reservation.id,
            JournalEntry.is_reversal == 0,
            JournalEntry.reversed_entry_id.is_(None),
        ).all()
        for entry in res_entries:
            self.reverse_entry(entry.id, created_by=created_by)

        # 2. عكس قيود العمولات
        comm_entries = self.db.query(JournalEntry).filter(
            JournalEntry.source_type == "commission",
            JournalEntry.source_id == reservation.id,
            JournalEntry.is_reversal == 0,
            JournalEntry.reversed_entry_id.is_(None),
        ).all()
        for entry in comm_entries:
            self.reverse_entry(entry.id, created_by=created_by)

        # 3. عكس قيود التحصيلات المرتبطة بالحجز (دة بيمثل Refund تلقائي)
        coll_ids = [ca.collection_id for ca in reservation.collection_allocations if ca.collection_id]
        if coll_ids:
            coll_entries = self.db.query(JournalEntry).filter(
                JournalEntry.source_type == "collection",
                JournalEntry.source_id.in_(coll_ids),
                JournalEntry.is_reversal == 0,
                JournalEntry.reversed_entry_id.is_(None),
            ).all()
            for entry in coll_entries:
                self.reverse_entry(entry.id, created_by=created_by)

        # 4. قيد الإسترداد الإضافي (اختياري — لو عاوز تسجل Refund زيادة عن التحصيلات)
        refund = D(refund_amount)
        if refund > DECIMAL_ZERO:
            self.post(
                lines=[(self._acc_id("opex"), refund, DECIMAL_ZERO),
                       (self._acc_id("treasury"), DECIMAL_ZERO, refund)],
                source_type="cancellation", source_id=reservation.id,
                description=f"استرداد إضافي حجز {reservation.booking_number}",
                created_by=created_by,
            )

        # 5. قيد رسوم الإلغاء (Cancellation Fee) — Dr Treasury / Cr Revenue
        fee = D(cancellation_fee)
        if fee > DECIMAL_ZERO:
            self.post(
                lines=[(self._acc_id("treasury"), fee, DECIMAL_ZERO),
                       (self._acc_id("sales_revenue"), DECIMAL_ZERO, fee)],
                source_type="cancellation", source_id=reservation.id,
                description=f"رسوم إلغاء حجز {reservation.booking_number}",
                created_by=created_by,
            )

        self.sync_all_caches()

    # -------- Auto-posting recipes --------
    def post_reservation_sale(self, reservation, created_by: str = "system"):
        amount = D(reservation.net_sale_price)
        if amount > DECIMAL_ZERO:
            self.post(
                lines=[(self._acc_id("ar"), amount, DECIMAL_ZERO),
                       (self._acc_id("sales_revenue"), DECIMAL_ZERO, amount)],
                source_type="reservation", source_id=reservation.id,
                description=f"إيراد حجز {reservation.booking_number}",
                created_by=created_by, entry_date=reservation.created_date,
                customer_id=reservation.customer_id, reservation_id=reservation.id,
            )

    def post_reservation_cost(self, reservation, created_by: str = "system"):
        amount = D(reservation.stay_cost)
        if amount > DECIMAL_ZERO:
            supplier_id = reservation.hotel.supplier_id if reservation.hotel else None
            self.post(
                lines=[(self._acc_id("cogs_hotels"), amount, DECIMAL_ZERO),
                       (self._acc_id("ap"), DECIMAL_ZERO, amount)],
                source_type="reservation", source_id=reservation.id,
                description=f"تكلفة حجز {reservation.booking_number}",
                created_by=created_by, entry_date=reservation.created_date,
                supplier_id=supplier_id, reservation_id=reservation.id,
            )

    def post_collection(self, collection, total_amount: Decimal, created_by: str = "system"):
        total = D(total_amount)
        if total <= DECIMAL_ZERO:
            return
        allocated = D(collection.allocated_amount)
        unallocated = total - allocated
        lines = [(self._acc_id("treasury"), total, DECIMAL_ZERO)]
        if allocated > DECIMAL_ZERO:
            lines.append((self._acc_id("ar"), DECIMAL_ZERO, allocated))
        if unallocated > DECIMAL_ZERO:
            lines.append((self._acc_id("suspense"), DECIMAL_ZERO, unallocated))
        self.post(
            lines=lines, source_type="collection", source_id=collection.id,
            description=f"تحصيل {collection.collection_number}: {collection.payer_name}",
            created_by=created_by, entry_date=collection.date,
            treasury_account_id=getattr(collection, 'account_id', None),
            customer_id=getattr(collection, 'customer_id', None),
        )

    def post_collection_allocation(self, collection, amount: Decimal, reservation, created_by: str = "system"):
        amt = D(amount)
        if amt <= DECIMAL_ZERO:
            return
        self.post(
            lines=[(self._acc_id("suspense"), amt, DECIMAL_ZERO),
                   (self._acc_id("ar"), DECIMAL_ZERO, amt)],
            source_type="collection", source_id=collection.id,
            description=f"توزيع تحصيل على حجز {reservation.booking_number}",
            created_by=created_by,
            customer_id=reservation.customer_id, reservation_id=reservation.id,
        )

    def post_supplier_payment(self, payment, total_amount: Decimal, created_by: str = "system"):
        total = D(total_amount)
        if total <= DECIMAL_ZERO:
            return
        allocated = D(payment.allocated_amount)
        unallocated = total - allocated
        lines = [(self._acc_id("ap"), allocated, DECIMAL_ZERO)]
        if unallocated > DECIMAL_ZERO:
            lines.append((self._acc_id("suspense"), unallocated, DECIMAL_ZERO))
        lines.append((self._acc_id("treasury"), DECIMAL_ZERO, total))
        sname = payment.supplier.name if payment.supplier else ""
        self.post(
            lines=lines, source_type="supplier_payment", source_id=payment.id,
            description=f"دفعة {payment.payment_number}: {sname}",
            created_by=created_by, entry_date=payment.date,
            treasury_account_id=getattr(payment, 'account_id', None),
            supplier_id=payment.supplier_id,
        )

    def post_expense(self, expense, created_by: str = "system"):
        amount = D(expense.amount)
        if amount <= DECIMAL_ZERO:
            return
        self.post(
            lines=[(self._acc_id("opex"), amount, DECIMAL_ZERO),
                   (self._acc_id("treasury"), DECIMAL_ZERO, amount)],
            source_type="expense", source_id=expense.id,
            description=f"مصروف: {expense.description or expense.category}",
            created_by=created_by, entry_date=expense.date,
            treasury_account_id=getattr(expense, 'account_id', None),
        )

    def post_withdrawal(self, withdrawal, created_by: str = "system"):
        amount = D(withdrawal.amount)
        if amount <= DECIMAL_ZERO:
            return
        emp_name = withdrawal.employee.name if withdrawal.employee else ""
        description = f"سحب موظف: {emp_name} ({withdrawal.withdrawal_type})"
        tacc_id = getattr(withdrawal, 'account_id', None)
        if withdrawal.withdrawal_type in ("salary",):
            self.post(
                lines=[(self._acc_id("salaries"), amount, DECIMAL_ZERO),
                       (self._acc_id("treasury"), DECIMAL_ZERO, amount)],
                source_type="withdrawal", source_id=withdrawal.id,
                description=description, created_by=created_by, entry_date=withdrawal.date,
                treasury_account_id=tacc_id,
            )
        else:
            self.post(
                lines=[(self._acc_id("commissions"), amount, DECIMAL_ZERO),
                       (self._acc_id("treasury"), DECIMAL_ZERO, amount)],
                source_type="withdrawal", source_id=withdrawal.id,
                description=description, created_by=created_by, entry_date=withdrawal.date,
                treasury_account_id=tacc_id,
            )

    def post_commission(self, reservation, amount: Decimal, commission_type: str,
                        recipient: str = "", created_by: str = "system"):
        amt = D(amount)
        if amt <= DECIMAL_ZERO:
            return
        # عمولة المورد التشغيلي (ops_supplier) بترجع تُحسب كمديونية على نفس المورد
        # في حساب الذمم الدائنة — أي نوع تاني (موظف/وكيل) مالوش كيان "مورد" فعلي
        # فبنسيب supplier_id فاضي وتفضل قيمتها داخل حساب العمولات العام بس.
        supplier_id = reservation.ops_supplier_id if commission_type == "ops_supplier" else None
        self.post(
            lines=[(self._acc_id("commissions"), amt, DECIMAL_ZERO),
                   (self._acc_id("ap"), DECIMAL_ZERO, amt)],
            source_type="commission", source_id=reservation.id,
            description=f"عمولة {commission_type} لحجز {reservation.booking_number}: {recipient}",
            created_by=created_by, entry_date=reservation.created_date,
            supplier_id=supplier_id, reservation_id=reservation.id,
        )

    def compute_account_balance(self, account):
        if account.children:
            return sum(self.compute_account_balance(child) for child in account.children)
        q = self.db.query(
            func.coalesce(func.sum(JournalLine.debit), 0),
            func.coalesce(func.sum(JournalLine.credit), 0),
        ).join(JournalEntry).filter(JournalLine.account_id == account.id)
        debit, credit = q.first()
        if account.account_type in ("asset", "expense"):
            journal_bal = D(debit) - D(credit)
        else:
            journal_bal = D(credit) - D(debit)
        return D(account.opening_balance) + journal_bal
