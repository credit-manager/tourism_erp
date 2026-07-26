from decimal import Decimal, ROUND_HALF_UP
from sqlalchemy import func

D = lambda x: Decimal(str(x)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
DECIMAL_ZERO = D(0)


class ReconciliationService:
    """مقارنة وتصحيح paid_to_office / paid_to_hotel مع التوزيعات الفعلية."""

    def __init__(self, db):
        self.db = db

    @staticmethod
    def sync_reservation_paid_fields(db, reservation):
        """تحديث paid_to_office و paid_to_hotel من مجموع التوزيعات.
        
        للحجوزات الملغية يتم التصفير (التوزيعات موجودة للأرشفة بس المبلغ مش نشط).
        """
        from models import CollectionAllocation, SupplierPaymentAllocation
        if reservation.status == "cancelled":
            reservation.paid_to_office = DECIMAL_ZERO
            reservation.paid_to_hotel = DECIMAL_ZERO
        else:
            total_collected = db.query(func.coalesce(func.sum(CollectionAllocation.amount), 0)) \
                .filter(CollectionAllocation.reservation_id == reservation.id).scalar()
            total_paid = db.query(func.coalesce(func.sum(SupplierPaymentAllocation.amount), 0)) \
                .filter(SupplierPaymentAllocation.reservation_id == reservation.id).scalar()
            reservation.paid_to_office = D(total_collected)
            reservation.paid_to_hotel = D(total_paid)
        db.flush()

    def compare(self, reservation):
        """مقارنة القيم المخزنة مع التوزيعات الفعلية."""
        from models import CollectionAllocation, SupplierPaymentAllocation
        total_collected = self.db.query(func.coalesce(func.sum(CollectionAllocation.amount), 0)) \
            .filter(CollectionAllocation.reservation_id == reservation.id).scalar()
        total_paid = self.db.query(func.coalesce(func.sum(SupplierPaymentAllocation.amount), 0)) \
            .filter(SupplierPaymentAllocation.reservation_id == reservation.id).scalar()
        return {
            "reservation_id": reservation.id,
            "booking_number": reservation.booking_number,
            "guest_name": reservation.guest_name,
            "stored_paid_to_office": D(reservation.paid_to_office),
            "allocated_paid_to_office": D(total_collected),
            "office_diff": D(reservation.paid_to_office) - D(total_collected),
            "stored_paid_to_hotel": D(reservation.paid_to_hotel),
            "allocated_paid_to_hotel": D(total_paid),
            "hotel_diff": D(reservation.paid_to_hotel) - D(total_paid),
        }

    def fix(self, reservation):
        """تصحيح القيم المخزنة لتتطابق مع التوزيعات."""
        self.sync_reservation_paid_fields(self.db, reservation)
        self.db.flush()

    def all_discrepancies(self):
        """تقرير بكل الحجوزات اللي فيها اختلافات."""
        from models import Reservation
        issues = []
        for r in self.db.query(Reservation).all():
            cmp = self.compare(r)
            if cmp["office_diff"] != DECIMAL_ZERO or cmp["hotel_diff"] != DECIMAL_ZERO:
                issues.append(cmp)
        return issues

    def supplier_balance_report(self):
        """
        مقارنة "المستحق للمورد" من مصدرين مختلفين لازم يطلعوا بنفس الرقم:

        1) رصيد المورد المحاسبي (Supplier.balance) — محسوب من قيود اليومية
           الفعلية (AP)، وبيشمل تكلفة الإقامة + أي عمولة مورد تشغيلي (ops_supplier)
           لسه ما اتدفعتش.
        2) مجموع "المتبقي للفندق" (remaining_to_hotel = stay_cost - paid_to_hotel)
           على كل حجوزات الفنادق التابعة لنفس المورد — ده بيشمل تكلفة
           الإقامة بس، من غير عمولات.

        عشان كده الفرق "الطبيعي" المتوقع بين الاتنين = مجموع عمولات ops_supplier
        اللي لسه ما اتدفعتش لنفس المورد. أي فرق زيادة عن كده معناه في حاجة
        اتسجلت غلط في مكان واحد بس (تعديل يدوي، خطأ إدخال...) ولازم تتراجع.
        """
        from models import Supplier, Hotel, Reservation, CommissionEntry
        from currency_utils import D as _D

        report = []
        suppliers = self.db.query(Supplier).all()
        for s in suppliers:
            hotel_ids = [h.id for h in self.db.query(Hotel).filter(Hotel.supplier_id == s.id).all()]
            reservations_owed = DECIMAL_ZERO
            if hotel_ids:
                rows = self.db.query(Reservation).filter(Reservation.hotel_id.in_(hotel_ids)).all()
                reservations_owed = sum((_D(r.remaining_to_hotel) for r in rows), DECIMAL_ZERO)

            unpaid_commission = self.db.query(func.coalesce(func.sum(CommissionEntry.calculated_amount), 0)) \
                .filter(
                    CommissionEntry.recipient_id == s.id,
                    CommissionEntry.recipient_type == "supplier",
                    CommissionEntry.status != "paid",
                ).scalar()
            unpaid_commission = _D(unpaid_commission)

            ledger_balance = _D(s.balance)
            expected = reservations_owed + unpaid_commission
            diff = ledger_balance - expected
            if abs(diff) > D("0.01"):
                report.append({
                    "supplier_id": s.id, "supplier_name": s.name,
                    "ledger_balance": ledger_balance,
                    "reservations_owed": reservations_owed,
                    "unpaid_commission": unpaid_commission,
                    "expected_total": expected,
                    "diff": diff,
                })
        return report
