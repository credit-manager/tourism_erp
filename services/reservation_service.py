import json
import datetime
from decimal import Decimal
from urllib.parse import quote
from currency_utils import D, DECIMAL_ZERO
from models import AuditLog, JournalEntry


class ReservationService:
    """Handles reservation modification with snapshot, accounting adjustment, and audit trail."""

    def __init__(self, db, user):
        self.db = db
        self.user = user

    # -------- الحقول المالية اللي بناخد لها Snapshot --------
    FINANCIAL_FIELDS = [
        "company_cost", "discount", "taxes", "stay_cost",
        "paid_to_office", "paid_to_hotel",
        "transportation_cost", "excursions_cost", "visa_cost",
        "insurance_cost", "other_services_cost",
        "employee_commission", "travel_agent_commission_amount",
        "sales_rep_commission_amount", "marketing_rep_commission_amount",
        "ops_supplier_commission_amount",
    ]
    RELATION_FIELDS = [
        "customer_id", "hotel_id", "ops_supplier_id", "employee_id",
        "travel_agent_id", "sales_rep_id", "marketing_rep_id",
    ]

    def _snapshot(self, reservation):
        """تسجيل القيم المالية والعلاقات القديمة قبل التعديل"""
        snap = {}
        for f in self.FINANCIAL_FIELDS:
            snap[f] = str(D(getattr(reservation, f, 0)))
        for f in self.RELATION_FIELDS:
            snap[f] = getattr(reservation, f, None)
        snap["net_sale_price"] = str(reservation.net_sale_price)
        snap["total_profit"] = str(reservation.total_profit)
        snap["services"] = [s.id for s in reservation.services]
        snap["service_ids"] = [s.id for s in reservation.services]
        return snap

    def _compute_diffs(self, old, new):
        """حساب الفرق بين القديم والجديد في كل بند مالي"""
        diffs = {}
        for f in self.FINANCIAL_FIELDS:
            o = D(old.get(f, 0))
            n = D(new.get(f, 0))
            if o != n:
                diffs[f] = {"old": str(o), "new": str(n), "diff": str(n - o)}
        # العلاقات
        for f in self.RELATION_FIELDS:
            if old.get(f) != new.get(f):
                diffs[f] = {"old": old.get(f), "new": new.get(f), "diff": "changed"}
        # net_sale_price
        o_nsp = D(old.get("net_sale_price", 0))
        n_nsp = D(new.get("net_sale_price", 0))
        if o_nsp != n_nsp:
            diffs["net_sale_price"] = {"old": str(o_nsp), "new": str(n_nsp), "diff": str(n_nsp - o_nsp)}
        # الخدمات
        if old.get("service_ids") != new.get("service_ids"):
            diffs["services"] = {"old": old.get("service_ids"), "new": new.get("service_ids"), "diff": "changed"}
        return diffs

    def _has_accounting_entries(self, reservation):
        """هل الحجز له قيود محاسبية سابقة؟"""
        return self.db.query(JournalEntry).filter(
            JournalEntry.source_type == "reservation",
            JournalEntry.source_id == reservation.id,
        ).count() > 0

    def _handle_accounting(self, reservation, old_vals):
        """تفويض إلى AccountingService.adjust_reservation لعكس القيود القديمة ونشر الجديدة"""
        from services.accounting_service import AccountingService
        AccountingService(self.db).adjust_reservation(
            reservation, old_vals, created_by=self.user.username,
        )

    def _log_modification(self, reservation, old_vals, new_vals, diffs, reason):
        """تسجيل AuditLog مع old/new values وسبب التعديل"""
        self.db.add(AuditLog(
            timestamp=datetime.datetime.utcnow(),
            username=getattr(self.user, "username", "?"),
            role=getattr(self.user, "role", "?"),
            action="adjustment",
            table_name="reservations",
            record_id=reservation.id,
            summary=f"تعديل الحجز {reservation.booking_number}: {len(diffs)} تغيير",
            old_values=json.dumps(old_vals, ensure_ascii=False, default=str),
            new_values=json.dumps(new_vals, ensure_ascii=False, default=str),
            reason=reason or "",
        ))

    def modify(self, reservation_id, form_data, reason=""):
        """الوظيفة الرئيسية: تعديل حجز مع Snapshot + محاسبة + Audit"""
        from routers.__init__ import _apply_reservation_fields
        from models import Reservation

        reservation = self.db.query(Reservation).get(reservation_id)
        if not reservation:
            raise ValueError(f"Reservation {reservation_id} not found")

        # 1. Snapshot القديم
        old_vals = self._snapshot(reservation)

        # 2. تطبيق الحقول الجديدة
        _apply_reservation_fields(reservation, form_data, self.db)

        # 3. Snapshot الجديد
        new_vals = self._snapshot(reservation)

        # 4. حساب الفروق
        diffs = self._compute_diffs(old_vals, new_vals)

        # 5. لو في تغيير مالي → عكس القيود القديمة + نشر الجديدة
        financial_keys = {"net_sale_price", "stay_cost", "employee_commission",
                          "travel_agent_commission_amount", "sales_rep_commission_amount",
                          "marketing_rep_commission_amount", "ops_supplier_commission_amount"}
        financial_changed = any(k in diffs for k in financial_keys)
        if financial_changed and self._has_accounting_entries(reservation):
            self._handle_accounting(reservation, old_vals)

        # 6. تسجيل الـ Audit
        self._log_modification(reservation, old_vals, new_vals, diffs, reason)

        self.db.flush()
        return diffs

    def _log_cancel(self, reservation, old_vals, reason, refund_amount, cancellation_fee):
        """تسجيل AuditLog للإلغاء"""
        cancel_data = dict(old_vals)
        cancel_data["refund_amount"] = str(refund_amount)
        cancel_data["cancellation_fee"] = str(cancellation_fee)
        cancel_data["cancelled_at"] = str(datetime.datetime.utcnow())
        cancel_data["cancelled_by"] = getattr(self.user, "username", "?")
        self.db.add(AuditLog(
            timestamp=datetime.datetime.utcnow(),
            username=getattr(self.user, "username", "?"),
            role=getattr(self.user, "role", "?"),
            action="cancel",
            table_name="reservations",
            record_id=reservation.id,
            summary=f"إلغاء الحجز {reservation.booking_number}",
            old_values=json.dumps(old_vals, ensure_ascii=False, default=str),
            new_values=json.dumps(cancel_data, ensure_ascii=False, default=str),
            reason=reason or "",
        ))

    def cancel(self, reservation_id, reason="", refund_amount=DECIMAL_ZERO,
               cancellation_fee=DECIMAL_ZERO):
        """إلغاء حجز مع عكس القيود المحاسبية والاحتفاظ بالسجل"""
        from models import Reservation
        from services.accounting_service import AccountingService

        reservation = self.db.query(Reservation).get(reservation_id)
        if not reservation:
            raise ValueError(f"Reservation {reservation_id} not found")
        if reservation.status == "cancelled":
            raise ValueError(f"Reservation {reservation.booking_number} already cancelled")

        old_vals = self._snapshot(reservation)

        # عكس القيود المحاسبية
        AccountingService(self.db).cancel_reservation(
            reservation,
            refund_amount=D(refund_amount),
            cancellation_fee=D(cancellation_fee),
            created_by=self.user.username,
        )

        # تحديث الحجز
        reservation.status = "cancelled"
        reservation.cancelled_at = datetime.datetime.utcnow()
        reservation.cancelled_by = getattr(self.user, "username", "?")
        reservation.cancellation_reason = reason or ""
        # تحديث الأرصدة من التوزيعات (الملغي يتصفّر تلقائياً)
        from services.reconciliation_service import ReconciliationService
        ReconciliationService.sync_reservation_paid_fields(self.db, reservation)

        self._log_cancel(reservation, old_vals, reason, refund_amount, cancellation_fee)
        self.db.flush()

    def hard_delete(self, reservation_id):
        """حذف نهائي — فقط للمسودات (draft) التي ليس عليها وثائق أو حركات مالية"""
        from models import Reservation

        reservation = self.db.query(Reservation).get(reservation_id)
        if not reservation:
            raise ValueError(f"Reservation {reservation_id} not found")

        if reservation.status != "draft":
            raise ValueError("لا يمكن الحذف النهائي إلا للمسودات (Draft)")

        if reservation.documents:
            raise ValueError("لا يمكن الحذف: يوجد مستندات مرتبطة بالحجز")

        if self._has_accounting_entries(reservation):
            raise ValueError("لا يمكن الحذف: يوجد قيود محاسبية للحجز")

        # تحقق من CollectionAllocation
        if reservation.collection_allocations:
            raise ValueError("لا يمكن الحذف: يوجد تحصيلات مرتبطة بالحجز")

        self.db.delete(reservation)
        self.db.flush()

    def check_credit_limit(self, customer_id, new_amount):
        from models import Customer, Reservation
        c = self.db.query(Customer).get(customer_id)
        if not c:
            return True, "", {}
        if c.credit_limit is None or D(c.credit_limit) <= DECIMAL_ZERO:
            return True, "", {}
        open_res = self.db.query(Reservation).filter(
            Reservation.customer_id == customer_id,
            Reservation.status.notin_(["cancelled", "closed"]),
        ).all()
        current_outstanding = sum(max(DECIMAL_ZERO, r.remaining_to_office) for r in open_res)
        new_total = current_outstanding + D(new_amount)
        available = D(c.credit_limit) - current_outstanding
        exceeded = new_total > D(c.credit_limit)
        details = {
            "credit_limit": float(c.credit_limit),
            "current_outstanding": float(current_outstanding),
            "new_amount": float(new_amount),
            "new_total": float(new_total),
            "available": max(0, float(available)),
            "exceeded": exceeded,
        }
        if exceeded:
            msg = (
                f"⚠️ تجاوز الحد الائتماني!\n"
                f"الحد الائتماني: {c.credit_limit:,.2f}\n"
                f"المستحق الحالي: {current_outstanding:,.2f}\n"
                f"المبلغ الجديد: {float(new_amount):,.2f}\n"
                f"الإجمالي: {new_total:,.2f}\n"
                f"المتاح: {max(0, float(available)):,.2f}"
            )
            return False, msg, details
        return True, "", details

    def create_reservation(self, form_data: dict) -> dict:
        from models import (Reservation, Hotel, Collection, CollectionAllocation, Service,
                            generate_booking_number, generate_collection_number, TreasuryTransaction)
        from routers.__init__ import _apply_reservation_fields, _detect_conflicts, _find_hotel_by_exact_name, _parse_date
        from services.commission_service import CommissionService

        data = dict(form_data)
        data["service_ids"] = [int(x) for x in form_data.getlist("service_ids")] if hasattr(form_data, "getlist") and form_data.getlist("service_ids") else (data.get("service_ids") or [])

        new_hotel_name = (data.get("new_hotel_name") or "").strip()
        if new_hotel_name:
            hotel = _find_hotel_by_exact_name(self.db, new_hotel_name)
            if not hotel:
                hotel = Hotel(name=new_hotel_name, price_per_night=0, available_rooms=0)
                self.db.add(hotel)
                self.db.flush()
            data["hotel_id"] = str(hotel.id)

        if not data.get("confirm_conflict"):
            conflicts = _detect_conflicts(self.db, data.get("guest_name"), data.get("hotel_id"),
                                          _parse_date(data.get("checkin_date")),
                                          _parse_date(data.get("checkout_date")),
                                          customer_id=int(data["customer_id"]) if data.get("customer_id") and str(data["customer_id"]).strip() else None)
            if conflicts:
                numbers = ", ".join(c.booking_number for c in conflicts)
                return {"conflict": True, "numbers": numbers}

        custom_num = str(data.get("custom_booking_number") or "").strip()
        if custom_num:
            existing = self.db.query(Reservation).filter(Reservation.booking_number == custom_num).first()
            if existing:
                return {"error": "duplicate_number", "number": custom_num}
            final_booking_number = custom_num
        else:
            final_booking_number = generate_booking_number(self.db)

        initial_paid = D(data.get("paid_to_office") or 0)
        reservation = Reservation(booking_number=final_booking_number, created_date=datetime.date.today())
        _apply_reservation_fields(reservation, data, self.db)
        if getattr(self.user, "role", "") != "admin":
            reservation.status = "pending"

        if reservation.reservation_type == "credit" and reservation.customer_id and not data.get("override_credit"):
            net_amount = D(reservation.company_cost or 0) - D(reservation.discount or 0) + D(reservation.taxes or 0) - initial_paid
            ok, msg, _ = self.check_credit_limit(reservation.customer_id, net_amount)
            if not ok and getattr(self.user, "role", "") != "admin":
                return {"credit_limit": True, "msg": quote(msg)}

        self.db.add(reservation)
        self.db.flush()

        CommissionService(self.db).apply_policies(reservation)

        if initial_paid > DECIMAL_ZERO:
            from services.treasury_service import TreasuryService, AccountNotSelectedError
            ts = TreasuryService(self.db)
            try:
                account = ts.resolve_account(None, "collection")
            except AccountNotSelectedError:
                account = None
            if account:
                self.db.add(TreasuryTransaction(
                    account_id=account.id, type="in", amount=initial_paid,
                    description=f"دفعة حجز {reservation.booking_number} - {reservation.guest_name}",
                    date=datetime.date.today()
                ))
                ts.add_balance(account.id, initial_paid)

        from services.accounting_service import AccountingService
        acc = AccountingService(self.db)
        acc.post_reservation_sale(reservation, created_by=getattr(self.user, "username", "system"))
        acc.post_reservation_cost(reservation, created_by=getattr(self.user, "username", "system"))
        if initial_paid > DECIMAL_ZERO:
            coll = Collection(collection_number=generate_collection_number(self.db),
                date=datetime.date.today(), customer_id=reservation.customer_id,
                payer_name=reservation.guest_name,
                total_amount=initial_paid,
                allocated_amount=initial_paid, unallocated_amount=DECIMAL_ZERO,
                account_id=account.id if account else None,
                notes=f"دفعة حجز {reservation.booking_number}")
            self.db.add(coll)
            self.db.flush()
            self.db.add(CollectionAllocation(collection_id=coll.id,
                reservation_id=reservation.id, amount=initial_paid,
                date=datetime.date.today()))
            acc.post_collection(coll, initial_paid, created_by=getattr(self.user, "username", "system"))
        from services.reconciliation_service import ReconciliationService
        ReconciliationService.sync_reservation_paid_fields(self.db, reservation)
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
                acc.post_commission(reservation, camt, ctype, created_by=getattr(self.user, "username", "system"))

        self.db.flush()
        if reservation.status == "confirmed":
            self._auto_create_tasks(reservation)

        return {"reservation": reservation}

    def _auto_create_tasks(self, reservation):
        from workflow_mappings import get_tasks_for_reservation
        from models import WorkflowTask, Service
        task_defs = get_tasks_for_reservation(reservation, self.db)
        existing_titles = set()
        for wt in self.db.query(WorkflowTask).filter(WorkflowTask.reservation_id == reservation.id).all():
            existing_titles.add(wt.title)
        for td, svc_name in task_defs:
            if td.title_ar in existing_titles or td.title_en in existing_titles:
                continue
            due = None
            if td.due_days_from_now is not None:
                due = datetime.date.today() + datetime.timedelta(days=td.due_days_from_now)
            elif reservation.checkin_date and td.due_days_from_checkin:
                due = reservation.checkin_date + datetime.timedelta(days=td.due_days_from_checkin)
            self.db.add(WorkflowTask(
                reservation_id=reservation.id,
                title=td.title_ar,
                description=f"{td.title_en} | {svc_name}" if svc_name else td.title_en,
                priority=td.priority,
                reminder=td.reminder,
                due_date=due,
            ))
        self.db.flush()

    def quick_pay(self, reservation_id: int, amount, payment_method: str = "cash", notes: str = ""):
        from models import Reservation, Collection, CollectionAllocation, TreasuryTransaction, generate_collection_number
        from services.reconciliation_service import ReconciliationService
        reservation = self.db.query(Reservation).get(reservation_id)
        d_amount = D(amount)
        if not reservation or d_amount <= DECIMAL_ZERO:
            raise ValueError("Invalid reservation or amount")
        owed_before = max(reservation.remaining_to_office, DECIMAL_ZERO)
        applied_amount = min(d_amount, owed_before)
        extra_amount = max(d_amount - applied_amount, DECIMAL_ZERO)
        from services.treasury_service import TreasuryService, AccountNotSelectedError
        ts = TreasuryService(self.db)
        try:
            account = ts.resolve_account(None, "collection")
        except AccountNotSelectedError:
            account = None
        collection = Collection(
            collection_number=generate_collection_number(self.db), date=datetime.date.today(),
            customer_id=reservation.customer_id, payer_name=reservation.guest_name, total_amount=d_amount,
            allocated_amount=applied_amount, unallocated_amount=extra_amount,
            account_id=account.id if account else None,
            notes=f"تحصيل سريع لحجز {reservation.booking_number} - طريقة الدفع: {payment_method}"
                  + (f" - {notes}" if notes else "")
        )
        self.db.add(collection)
        self.db.flush()
        if applied_amount > DECIMAL_ZERO:
            self.db.add(CollectionAllocation(collection_id=collection.id, reservation_id=reservation.id,
                                             amount=applied_amount, date=datetime.date.today()))
        if account:
            self.db.add(TreasuryTransaction(
                account_id=account.id, type="in", amount=d_amount,
                description=f"تحصيل حجز {reservation.booking_number} - {reservation.guest_name} - {payment_method}",
                date=datetime.date.today()
            ))
            ts.add_balance(account.id, d_amount)
        from services.accounting_service import AccountingService
        acc = AccountingService(self.db)
        acc.post_collection(collection, d_amount, created_by=getattr(self.user, "username", "system"))
        ReconciliationService.sync_reservation_paid_fields(self.db, reservation)
        self.db.flush()

    def duplicate(self, reservation_id: int) -> "Reservation":
        from models import Reservation, generate_booking_number
        from services.commission_service import CommissionService
        src = self.db.query(Reservation).get(reservation_id)
        if not src:
            raise ValueError(f"Reservation {reservation_id} not found")
        clone = Reservation(
            booking_number=generate_booking_number(self.db), created_date=datetime.date.today(),
            customer_id=src.customer_id, guest_name=src.guest_name, email=src.email,
            is_vip=src.is_vip, special_requests=src.special_requests,
            reference_number="", source=src.source, priority=src.priority,
            internal_notes=src.internal_notes,
            checkin_date=src.checkin_date, checkout_date=src.checkout_date,
            passport_no=src.passport_no, phone=src.phone, nationality=src.nationality,
            country=src.country, adults=src.adults, children=src.children,
            children_ages=src.children_ages, hotel_id=src.hotel_id,
            room_type=src.room_type, stay_type=src.stay_type, meal_plan=src.meal_plan,
            room_count=src.room_count, extra_bed=src.extra_bed,
            checkin_time=src.checkin_time, checkout_time=src.checkout_time,
            stay_cost=src.stay_cost, paid_to_hotel=DECIMAL_ZERO,
            company_cost=src.company_cost, discount=src.discount, taxes=src.taxes,
            paid_to_office=DECIMAL_ZERO,
            transportation_cost=src.transportation_cost,
            excursions_cost=src.excursions_cost, visa_cost=src.visa_cost,
            insurance_cost=src.insurance_cost,
            other_services_cost=src.other_services_cost,
            flight_number=src.flight_number, pickup_time=src.pickup_time,
            dropoff_time=src.dropoff_time, driver_name=src.driver_name,
            guide_name=src.guide_name, vehicle_info=src.vehicle_info,
            ops_supplier_id=src.ops_supplier_id, employee_id=src.employee_id,
            reservation_rep_commission_type=src.reservation_rep_commission_type,
            reservation_rep_commission_value=src.reservation_rep_commission_value,
            travel_agent_id=src.travel_agent_id,
            travel_agent_commission_type=src.travel_agent_commission_type,
            travel_agent_commission_value=src.travel_agent_commission_value,
            sales_rep_id=src.sales_rep_id,
            sales_rep_commission_type=src.sales_rep_commission_type,
            sales_rep_commission_value=src.sales_rep_commission_value,
            status="draft", notes=src.notes,
        )
        base = clone.total_profit
        clone.employee_commission = Reservation.compute_commission(
            clone.reservation_rep_commission_type, clone.reservation_rep_commission_value, base
        ) if clone.employee_id else DECIMAL_ZERO
        clone.travel_agent_commission_amount = Reservation.compute_commission(
            clone.travel_agent_commission_type, clone.travel_agent_commission_value, base
        ) if clone.travel_agent_id else DECIMAL_ZERO
        clone.sales_rep_commission_amount = Reservation.compute_commission(
            clone.sales_rep_commission_type, clone.sales_rep_commission_value, base
        ) if clone.sales_rep_id else DECIMAL_ZERO
        clone.services = list(src.services)
        self.db.add(clone)
        self.db.flush()
        CommissionService(self.db).apply_policies(clone)
        self.db.flush()
        return clone

    def confirm(self, reservation_id: int):
        from models import Reservation
        reservation = self.db.query(Reservation).get(reservation_id)
        if not reservation:
            raise ValueError(f"Reservation {reservation_id} not found")
        if reservation.reservation_type == "credit" and reservation.customer_id:
            net_amount = D(reservation.company_cost or 0) - D(reservation.discount or 0) + D(reservation.taxes or 0)
            ok, msg, _ = self.check_credit_limit(reservation.customer_id, net_amount)
            if not ok and getattr(self.user, "role", "") != "admin":
                return {"credit_limit": True, "msg": quote(msg)}
        reservation.status = "confirmed"
        self.db.flush()
