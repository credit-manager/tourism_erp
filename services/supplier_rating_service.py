import datetime
from decimal import Decimal, ROUND_HALF_UP
from sqlalchemy import func
from models import Supplier, SupplierConfirmation, SupplierConfirmationLine, SupplierInvoice, SupplierInvoiceLine, Reservation, Hotel
from currency_utils import D, DECIMAL_ZERO

D100 = lambda x: int(round(float(Decimal(str(x)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)), 0))
CLAMP = lambda v: max(0, min(100, int(round(v))))


class SupplierRatingService:

    def __init__(self, db):
        self.db = db

    def compute_all(self, supplier_id=None):
        suppliers = self.db.query(Supplier)
        if supplier_id:
            suppliers = suppliers.filter(Supplier.id == supplier_id)
        results = []
        for s in suppliers.all():
            rating = self.compute_one(s)
            if rating:
                results.append(rating)
        results.sort(key=lambda r: r["overall"], reverse=True)
        return results

    def compute_one(self, supplier):
        s = supplier
        cost_accuracy = self._cost_accuracy(s)
        confirmation_speed = self._confirmation_speed(s)
        service_quality = self._service_quality(s)
        cancellation_rate = self._cancellation_rate(s)
        complaints = self._complaints(s)
        invoice_compliance = self._invoice_compliance(s)
        response_time = self._response_time(s)

        dimensions = {
            "cost_accuracy": {"label_ar": "دقة التكلفة", "label_en": "Cost Accuracy", "score": cost_accuracy, "weight": 20},
            "confirmation_speed": {"label_ar": "سرعة التأكيد", "label_en": "Confirmation Speed", "score": confirmation_speed, "weight": 15},
            "service_quality": {"label_ar": "جودة الخدمة", "label_en": "Service Quality", "score": service_quality, "weight": 20},
            "cancellation_rate": {"label_ar": "معدل الإلغاء", "label_en": "Cancellation Rate", "score": cancellation_rate, "weight": 15},
            "complaints": {"label_ar": "الشكاوى", "label_en": "Complaints", "score": complaints, "weight": 10},
            "invoice_compliance": {"label_ar": "الالتزام بالفواتير", "label_en": "Invoice Compliance", "score": invoice_compliance, "weight": 10},
            "response_time": {"label_ar": "سرعة الاستجابة", "label_en": "Response Time", "score": response_time, "weight": 10},
        }

        total_weight = sum(d["weight"] for d in dimensions.values())
        overall = sum(d["score"] * d["weight"] for d in dimensions.values()) / total_weight if total_weight else 0
        overall = CLAMP(overall)

        # city info for suggestions
        city = self._supplier_city(s)

        return {
            "supplier_id": s.id,
            "supplier_name": s.name,
            "supplier_type": s.type,
            "city": city,
            "overall": overall,
            "dimensions": dimensions,
            "data_points": self._data_count(s),
        }

    def _cost_accuracy(self, s):
        lines = self.db.query(SupplierInvoiceLine).join(SupplierInvoice).filter(
            SupplierInvoice.supplier_id == s.id,
            SupplierInvoiceLine.expected_cost > 0,
        ).all()
        if not lines:
            return 50
        diffs = []
        for ln in lines:
            exp = float(D(ln.expected_cost or 0))
            inv = float(D(ln.invoiced_cost or 0))
            if exp > 0:
                diff_pct = abs(inv - exp) / exp
                diffs.append(diff_pct)
        if not diffs:
            return 50
        avg_diff = sum(diffs) / len(diffs)
        return CLAMP(100 - avg_diff * 100)

    def _confirmation_speed(self, s):
        confirmations = self.db.query(SupplierConfirmation).filter(
            SupplierConfirmation.supplier_id == s.id,
            SupplierConfirmation.status != "draft",
            SupplierConfirmation.confirmed_at.isnot(None),
        ).all()
        if not confirmations:
            return 50
        scores = []
        for c in confirmations:
            if c.confirmed_at and c.created_at:
                diff_days = (c.confirmed_at - c.created_at).days
                if diff_days <= 0:
                    scores.append(100)
                elif diff_days <= 1:
                    scores.append(95)
                elif diff_days <= 2:
                    scores.append(85)
                elif diff_days <= 5:
                    scores.append(65)
                elif diff_days <= 10:
                    scores.append(45)
                else:
                    scores.append(25)
        if not scores:
            return 50
        return CLAMP(sum(scores) / len(scores))

    def _service_quality(self, s):
        hotel_ids = [h.id for h in s.hotels]
        if not hotel_ids:
            return 50
        reservations = self.db.query(Reservation).filter(
            Reservation.hotel_id.in_(hotel_ids),
        ).all()
        if not reservations:
            return 50
        good = sum(1 for r in reservations if r.status in ("confirmed", "checked_in", "checked_out", "closed"))
        bad = sum(1 for r in reservations if r.status in ("cancelled",))
        total = good + bad
        if total == 0:
            return 50
        return CLAMP(good / total * 100)

    def _cancellation_rate(self, s):
        confirmations = self.db.query(SupplierConfirmation).filter(
            SupplierConfirmation.supplier_id == s.id,
        ).all()
        invoices = self.db.query(SupplierInvoice).filter(
            SupplierInvoice.supplier_id == s.id,
        ).all()
        total = len(confirmations) + len(invoices)
        if total == 0:
            return 50
        cancelled = sum(1 for c in confirmations if c.status == "cancelled")
        cancelled += sum(1 for inv in invoices if inv.status == "cancelled")
        return CLAMP((1 - cancelled / total) * 100)

    def _complaints(self, s):
        hotel_ids = [h.id for h in s.hotels]
        score = 80
        if hotel_ids:
            cancelled_res = self.db.query(Reservation).filter(
                Reservation.hotel_id.in_(hotel_ids),
                Reservation.status == "cancelled",
                Reservation.cancellation_reason.isnot(None),
                Reservation.cancellation_reason != "",
            ).all()
            flagged = 0
            keywords = ["شكوى", "مشكلة", "سيء", "تأخير", "خطأ", "complaint", "problem", "bad", "delay", "error"]
            for r in cancelled_res:
                reason = (r.cancellation_reason or "").lower()
                if any(k in reason for k in keywords):
                    flagged += 1
            if cancelled_res:
                penalty = (flagged / len(cancelled_res)) * 40
                score = max(20, int(round(80 - penalty)))
        return CLAMP(score)

    def _invoice_compliance(self, s):
        invoices = self.db.query(SupplierInvoice).filter(
            SupplierInvoice.supplier_id == s.id,
        ).all()
        if not invoices:
            return 50
        status_score = 0
        for inv in invoices:
            if inv.status in ("posted", "approved"):
                status_score += 100
            elif inv.status == "draft":
                status_score += 50
            elif inv.status == "cancelled":
                status_score += 20
            else:
                status_score += 70
        avg_status = status_score / len(invoices)

        lines = self.db.query(SupplierInvoiceLine).join(SupplierInvoice).filter(
            SupplierInvoice.supplier_id == s.id,
            SupplierInvoiceLine.expected_cost > 0,
        ).all()
        cost_score = 50
        if lines:
            diffs = []
            for ln in lines:
                exp = float(D(ln.expected_cost or 0))
                inv = float(D(ln.invoiced_cost or 0))
                if exp > 0:
                    diffs.append(abs(inv - exp) / exp)
            if diffs:
                avg_diff = sum(diffs) / len(diffs)
                cost_score = CLAMP(100 - avg_diff * 100)

        return CLAMP(avg_status * 0.5 + cost_score * 0.5)

    def _response_time(self, s):
        lines = self.db.query(SupplierConfirmationLine).join(SupplierConfirmation).filter(
            SupplierConfirmation.supplier_id == s.id,
            SupplierConfirmation.status != "draft",
        ).all()
        if not lines:
            return 50
        scores = []
        for ln in lines:
            res = ln.reservation
            if res and res.checkin_date and ln.confirmation and ln.confirmation.confirmed_at:
                try:
                    checkin = res.checkin_date
                    if hasattr(checkin, "date"):
                        checkin = checkin.date() if hasattr(checkin, "date") else checkin
                    diff_days = (ln.confirmation.confirmed_at.date() - checkin).days
                    if diff_days >= 14:
                        scores.append(100)
                    elif diff_days >= 7:
                        scores.append(85)
                    elif diff_days >= 3:
                        scores.append(65)
                    elif diff_days >= 1:
                        scores.append(45)
                    else:
                        scores.append(25)
                except:
                    pass
        if not scores:
            return 50
        return CLAMP(sum(scores) / len(scores))

    def _supplier_city(self, s):
        hotels = s.hotels
        if hotels:
            for h in hotels:
                if h.city:
                    return h.city
        return ""

    def _data_count(self, s):
        confirmations = self.db.query(SupplierConfirmation).filter(SupplierConfirmation.supplier_id == s.id).count()
        invoices = self.db.query(SupplierInvoice).filter(SupplierInvoice.supplier_id == s.id).count()
        return confirmations + invoices

    def get_suggestions(self, supplier_type=None, city=None):
        results = self.compute_all()
        filtered = results
        if supplier_type:
            filtered = [r for r in filtered if r["supplier_type"] == supplier_type]
        suggestions = {}

        if city:
            city_filtered = [r for r in filtered if r["city"] and r["city"].lower() == city.lower()]
            if city_filtered:
                suggestions[city] = city_filtered[:3]

        by_city = {}
        for r in filtered:
            c = r["city"] or "أخرى"
            if c not in by_city:
                by_city[c] = []
            by_city[c].append(r)

        for c, items in by_city.items():
            items.sort(key=lambda x: x["overall"], reverse=True)
            if len(items) > 1:
                suggestions[c] = items[:3]

        if not suggestions:
            suggestions["الكل"] = filtered[:5]

        return suggestions
