import datetime
from fastapi import Request, Depends
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from sqlalchemy import func
from currency_utils import D, DECIMAL_ZERO

from models import Reservation, Employee, Expense, TreasuryAccount, AuditLog, STATUS_LABELS, Account, JournalEntry, JournalLine, Customer
from . import templates, get_db, _employee_period_earnings


def setup_dashboard_routes(app):
    @app.get("/", response_class=HTMLResponse)
    def dashboard(request: Request, db: Session = Depends(get_db)):
        today = datetime.date.today()
        month_start = today.replace(day=1)

        all_reservations = db.query(Reservation).all()

        def _bal(key):
            from services.accounting_service import AccountingService
            asc = AccountingService(db)
            a = db.query(Account).filter(Account.key == key).first()
            return asc.compute_account_balance(a) if a else DECIMAL_ZERO

        total_revenue = _bal("sales_revenue")
        total_hotel_cost = _bal("cogs_hotels")
        total_commissions = _bal("commissions")
        total_expenses = _bal("opex")
        net_profit = (total_revenue - total_hotel_cost) - total_commissions - total_expenses

        month_reservations = [r for r in all_reservations if r.created_date and r.created_date >= month_start]
        monthly_revenue = sum(D(r.company_cost) for r in month_reservations)
        monthly_cost = sum(D(r.stay_cost) for r in month_reservations)
        monthly_profit = monthly_revenue - monthly_cost

        active_reservations = [r for r in all_reservations if not r.is_paid_in_full]
        pending_payments = sum(r.remaining_to_office for r in active_reservations)
        confirmed_trips = sum(1 for r in all_reservations if r.checkin_date and r.checkin_date >= today)
        treasury_total = _bal("treasury")

        days = [(today - datetime.timedelta(days=i)) for i in range(13, -1, -1)]
        daily_counts, daily_revenue = [], []
        for d in days:
            day_res = [r for r in all_reservations if r.created_date == d]
            daily_counts.append(len(day_res))
            daily_revenue.append(sum(D(r.company_cost) for r in day_res))
        chart_labels = [d.strftime("%d/%m") for d in days]

        last7 = sum(daily_counts[-7:])
        prev7 = sum(daily_counts[-14:-7]) or 1
        bookings_trend = round(((last7 - prev7) / prev7) * 100, 1)
        rev_last7 = sum(daily_revenue[-7:])
        rev_prev7 = sum(daily_revenue[-14:-7]) or 1
        revenue_trend = round(((rev_last7 - rev_prev7) / rev_prev7) * 100, 1)

        hotel_revenue, destination_revenue = {}, {}
        for r in all_reservations:
            hname = r.hotel.name if r.hotel else "بدون فندق"
            hotel_revenue[hname] = hotel_revenue.get(hname, DECIMAL_ZERO) + D(r.company_cost)
            city = r.hotel.city if r.hotel and r.hotel.city else "غير محدد"
            destination_revenue[city] = destination_revenue.get(city, DECIMAL_ZERO) + D(r.company_cost)
        top_hotels = sorted(hotel_revenue.items(), key=lambda x: x[1], reverse=True)[:5]
        hotel_labels = [h[0] for h in top_hotels]
        hotel_values = [round(h[1], 2) for h in top_hotels]
        top_destinations = sorted(destination_revenue.items(), key=lambda x: x[1], reverse=True)[:5]

        employees = db.query(Employee).all()
        agent_totals = []
        for emp in employees:
            total = _employee_period_earnings(db, emp.id, month_start, today)
            if total > 0:
                agent_totals.append((emp.name, total))
        top_agents = sorted(agent_totals, key=lambda x: x[1], reverse=True)[:5]

        today_departures = [r for r in all_reservations if r.checkin_date == today]
        outstanding = sorted(active_reservations, key=lambda r: r.remaining_to_office, reverse=True)[:5]
        recent_activity = db.query(AuditLog).filter(AuditLog.role != "owner").order_by(AuditLog.id.desc()).limit(6).all()

        expenses_by_category = {}
        for e in db.query(Expense).filter(Expense.date >= month_start).all():
            expenses_by_category[e.category] = expenses_by_category.get(e.category, DECIMAL_ZERO) + D(e.amount)

        today_checkouts = [r for r in all_reservations if r.checkout_date == today]
        status_counts = {}
        for r in all_reservations:
            status_counts[r.status or "confirmed"] = status_counts.get(r.status or "confirmed", 0) + 1
        source_counts = {}
        for r in all_reservations:
            source_counts[r.source or "direct"] = source_counts.get(r.source or "direct", 0) + 1
        daily_cost = []
        for d in days:
            day_res = [r for r in all_reservations if r.created_date == d]
            daily_cost.append(sum(D(r.stay_cost) for r in day_res))
        gross_profit_total = total_revenue - total_hotel_cost
        profit_margin = round((net_profit / total_revenue) * 100, 1) if total_revenue else DECIMAL_ZERO
        pending_count = sum(1 for r in all_reservations if r.status == "pending")
        cancelled_count = sum(1 for r in all_reservations if r.status == "cancelled")
        confirmed_count = sum(1 for r in all_reservations if r.status in ("confirmed", "checked_in", "checked_out"))

        # Overdue credit reservations
        overdue_reservations = [r for r in all_reservations if r.reservation_type == "credit"
                                and r.payment_due_date and r.payment_due_date < today
                                and r.status not in ("cancelled", "closed")
                                and r.remaining_to_office > DECIMAL_ZERO]
        overdue_total = sum(r.remaining_to_office for r in overdue_reservations)

        # Customers exceeding credit limit
        credit_customers = db.query(Customer).filter(Customer.credit_limit > DECIMAL_ZERO).all()
        exceeded_customers = []
        for c in credit_customers:
            open_res = [r for r in all_reservations if r.customer_id == c.id and r.status not in ("cancelled", "closed")]
            outstanding = sum(max(DECIMAL_ZERO, r.remaining_to_office) for r in open_res)
            if outstanding > D(c.credit_limit):
                exceeded_customers.append({"name": c.name, "id": c.id, "outstanding": outstanding, "limit": c.credit_limit})

        return templates.TemplateResponse(request, "dashboard.html", {
            "request": request, "page_title": None, "active": "home",
            "total_revenue": total_revenue, "total_expenses": total_expenses, "net_profit": net_profit,
            "monthly_profit": monthly_profit, "bookings_count": len(all_reservations),
            "active_count": len(active_reservations), "pending_payments": pending_payments,
            "confirmed_trips": confirmed_trips, "treasury_total": treasury_total,
            "bookings_trend": bookings_trend, "revenue_trend": revenue_trend,
            "recent_bookings": all_reservations[-8:][::-1],
            "chart_labels": chart_labels, "daily_counts": daily_counts, "daily_revenue": daily_revenue,
            "daily_cost": daily_cost, "hotel_labels": hotel_labels, "hotel_values": hotel_values,
            "top_destinations": top_destinations, "top_agents": top_agents,
            "today_departures": today_departures, "today_checkouts": today_checkouts, "outstanding": outstanding,
            "recent_activity": recent_activity, "expenses_by_category": expenses_by_category,
            "status_counts": status_counts, "source_counts": source_counts,
            "gross_profit_total": gross_profit_total, "profit_margin": profit_margin,
            "pending_count": pending_count, "cancelled_count": cancelled_count, "confirmed_count": confirmed_count,
            "STATUS_LABELS": STATUS_LABELS,
            "overdue_reservations": overdue_reservations,
            "overdue_total": overdue_total,
            "exceeded_customers": exceeded_customers,
        })
