"""
InsightsService
================
طبقة تحليل حقيقية مبنية على قواعد وإحصاء صريح (مش صندوق أسود) — بتجاوب
على سؤالين عمليين:

1) هل فيه دفعات مكررة محتملة؟ (نفس الجهة + نفس المبلغ تقريبًا + خلال
   فترة قصيرة) — قاعدة كشف كلاسيكية معروفة في أنظمة المراجعة الداخلية.

2) التدفق النقدي المتوقع للأسابيع الجاية = اتجاه تاريخي (متوسط صافي
   حركة الخزنة أسبوعيًا في آخر فترة) + مستحقات معروفة فعليًا (AR/AP
   غير محصّلة على حجوزات حقيقية) — مش تنبؤ "ذكاء اصطناعي" غامض، أرقام
   قابلة للتتبع لمصدرها.
"""
import datetime
from decimal import Decimal
from sqlalchemy import func
from currency_utils import D, DECIMAL_ZERO
from models import SupplierPayment, Collection, Expense, TreasuryTransaction, Reservation


class InsightsService:
    def __init__(self, db):
        self.db = db

    # ─────────────────────────── كشف الدفعات المكررة ───────────────────────────

    def detect_duplicate_supplier_payments(self, window_days: int = 3):
        return self._detect_duplicates(
            SupplierPayment, "supplier_id", "total_amount", "date", "payment_number", window_days
        )

    def detect_duplicate_collections(self, window_days: int = 3):
        return self._detect_duplicates(
            Collection, "customer_id", "total_amount", "date", "collection_number", window_days
        )

    def detect_duplicate_expenses(self, window_days: int = 3):
        return self._detect_duplicates(
            Expense, "category", "amount", "date", "id", window_days
        )

    def _detect_duplicates(self, model, party_field, amount_field, date_field, ref_field, window_days):
        """يقارن كل سجل بالسجلات التانية لنفس الجهة اللي قيمتها قريبة (±1 جنيه)
        وتاريخها قريب (خلال window_days)، ويطلع أزواج الاشتباه بدون تكرار."""
        rows = self.db.query(model).order_by(getattr(model, date_field)).all()
        suspects = []
        seen_pairs = set()
        for i, a in enumerate(rows):
            a_amt = D(getattr(a, amount_field))
            a_date = getattr(a, date_field)
            a_party = getattr(a, party_field)
            if a_amt <= DECIMAL_ZERO or not a_date:
                continue
            for b in rows[i + 1:]:
                b_date = getattr(b, date_field)
                if not b_date:
                    continue
                if (b_date - a_date).days > window_days:
                    break  # الليستة متسورتة بالتاريخ، مفيش داعي نكمل أبعد
                if getattr(b, party_field) != a_party:
                    continue
                b_amt = D(getattr(b, amount_field))
                if abs(b_amt - a_amt) > D("1.00"):
                    continue
                pair_key = tuple(sorted([a.id, b.id]))
                if pair_key in seen_pairs:
                    continue
                seen_pairs.add(pair_key)
                suspects.append({
                    "model": model.__tablename__,
                    "a_id": a.id, "a_ref": getattr(a, ref_field, a.id), "a_date": a_date, "a_amount": a_amt,
                    "b_id": b.id, "b_ref": getattr(b, ref_field, b.id), "b_date": b_date, "b_amount": b_amt,
                    "days_apart": (b_date - a_date).days,
                })
        return suspects

    def all_duplicate_alerts(self):
        alerts = []
        for kind, label_ar, label_en, items in [
            ("supplier_payment", "دفعة مورد", "Supplier Payment", self.detect_duplicate_supplier_payments()),
            ("collection", "تحصيل", "Collection", self.detect_duplicate_collections()),
            ("expense", "مصروف", "Expense", self.detect_duplicate_expenses()),
        ]:
            for it in items:
                it["kind"] = kind
                it["label_ar"] = label_ar
                it["label_en"] = label_en
                alerts.append(it)
        return alerts

    # ─────────────────────────── توقع التدفق النقدي ───────────────────────────

    def _historical_weekly_net(self, weeks_back: int = 8):
        """صافي حركة الخزنة (دخول - خروج) لكل أسبوع من آخر weeks_back أسبوع،
        من حركات الخزنة الفعلية المُرحّلة."""
        today = datetime.date.today()
        start = today - datetime.timedelta(weeks=weeks_back)
        rows = self.db.query(TreasuryTransaction).filter(TreasuryTransaction.date >= start).all()
        buckets = {}
        for r in rows:
            week_start = r.date - datetime.timedelta(days=r.date.weekday())
            amt = D(r.amount) if r.type == "in" else -D(r.amount)
            buckets[week_start] = buckets.get(week_start, DECIMAL_ZERO) + amt
        return buckets

    def cash_flow_forecast(self, weeks_ahead: int = 8):
        """توقع صافي التدفق النقدي للأسابيع الجاية:
        - أسابيع فيها مستحقات معروفة فعليًا (AR غير محصّل، AP غير مسدّد) بتتحط
          في أقرب أسبوعين (افتراض تحفّظي: المتوقع تحصيله/دفعه قريب).
        - باقي الأسابيع بتتوقع من متوسط الاتجاه التاريخي لآخر 8 أسابيع.
        كل رقم هنا قابل للتتبع لمصدره — مفيش صندوق أسود."""
        history = self._historical_weekly_net(weeks_back=8)
        hist_values = list(history.values())
        avg_weekly_net = (sum(hist_values) / len(hist_values)) if hist_values else DECIMAL_ZERO

        # ملحوظة: net_sale_price و remaining_to_hotel خصائص بايثون (@property) مش
        # أعمدة حقيقية في القاعدة، فمينفعش نستخدمهم جوه استعلام SQL مباشرة —
        # بنستخدم نفس معادلتهم بالأعمدة الحقيقية (company_cost/discount/taxes,
        # stay_cost/paid_to_hotel) للحصول على نفس النتيجة.
        total_ar = self.db.query(func.coalesce(func.sum(
            Reservation.company_cost - Reservation.discount + Reservation.taxes - Reservation.paid_to_office
        ), 0)).filter(Reservation.status.in_(["confirmed", "completed"])).scalar()
        total_ap = self.db.query(func.coalesce(func.sum(
            Reservation.stay_cost - Reservation.paid_to_hotel
        ), 0)).filter(Reservation.status.in_(["confirmed", "completed"])).scalar()
        total_ar = D(total_ar)
        total_ap = D(total_ap)

        today = datetime.date.today()
        weeks = []
        running = DECIMAL_ZERO
        for w in range(weeks_ahead):
            week_start = today + datetime.timedelta(weeks=w)
            projected = avg_weekly_net
            note = "اتجاه تاريخي"
            if w == 0:
                projected += total_ar * D("0.5")  # افتراض تحفّظي: نص المستحق يتحصّل قريب
                note = "اتجاه تاريخي + نص المستحقات المعروفة (AR)"
            elif w == 1:
                projected -= total_ap * D("0.5")
                note = "اتجاه تاريخي − نص المستحقات للموردين (AP)"
            running += projected
            weeks.append({
                "week_start": week_start, "projected_net": projected,
                "running_balance_change": running, "note": note,
            })
        return {
            "weeks": weeks,
            "avg_weekly_net_historical": avg_weekly_net,
            "total_ar_outstanding": total_ar,
            "total_ap_outstanding": total_ap,
            "history_weeks_used": len(hist_values),
        }
