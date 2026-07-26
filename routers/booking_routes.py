import datetime
from fastapi import Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from currency_utils import D, DECIMAL_ZERO

from models import Booking, Customer, Employee, Supplier, TreasuryAccount, TreasuryTransaction, Currency
from . import templates, get_db
import auth


def setup_booking_routes(app):
    @app.get("/bookings", response_class=HTMLResponse)
    def bookings_page(request: Request, db: Session = Depends(get_db)):
        bookings = db.query(Booking).order_by(Booking.id.desc()).all()
        customers = db.query(Customer).all()
        employees = db.query(Employee).all()
        suppliers = db.query(Supplier).all()
        accounts = db.query(TreasuryAccount).all()
        currencies = db.query(Currency).all()
        return templates.TemplateResponse(request, "bookings.html", {
            "request": request, "bookings": bookings, "customers": customers,
            "employees": employees, "suppliers": suppliers, "accounts": accounts,
            "currencies": currencies,
            "page_title": "الحجوزات", "active": "bookings"
        })

    @app.post("/bookings/add")
    def add_booking(customer_id: int = Form(...), employee_id: int = Form(None), supplier_id: int = Form(None),
                    booking_type: str = Form("internal"), total_price: float = Form(0), supplier_cost: float = Form(0),
                    account_id: int = Form(None), currency_id: int = Form(None),
                    exchange_rate: float = Form(1), db: Session = Depends(get_db),
                    user=Depends(auth.require_permission("bookings.manage"))):
        d_total_price = D(total_price)
        d_supplier_cost = D(supplier_cost)
        d_rate = D(exchange_rate)
        amount_currency = d_total_price
        amount_base = d_total_price * d_rate if d_rate > 0 else d_total_price
        company_commission = d_total_price - d_supplier_cost
        employee_commission = DECIMAL_ZERO
        if employee_id:
            emp = db.query(Employee).get(employee_id)
            if emp:
                employee_commission = company_commission * D(emp.commission_rate) / D(100)
        booking = Booking(
            customer_id=customer_id, employee_id=employee_id, supplier_id=supplier_id,
            booking_type=booking_type, total_price=d_total_price, supplier_cost=d_supplier_cost,
            company_commission=company_commission, employee_commission=employee_commission,
            currency_id=currency_id, amount_currency=amount_currency, amount_base=amount_base,
            exchange_rate=d_rate, date=datetime.date.today(), status="confirmed", account_id=account_id,
        )
        db.add(booking)
        db.flush()
        from services.treasury_service import TreasuryService, AccountNotSelectedError
        ts = TreasuryService(db)
        try:
            account = ts.resolve_account(booking.account_id, "collection")
        except AccountNotSelectedError:
            account = None
        if account:
            if not booking.account_id:
                booking.account_id = account.id
            db.add(TreasuryTransaction(
                account_id=account.id, type="in", amount=d_total_price,
                description=f"حجز جديد - عميل #{customer_id}", date=datetime.date.today()
            ))
            ts.add_balance(account.id, d_total_price)
        db.commit()
        return RedirectResponse("/bookings", status_code=303)
