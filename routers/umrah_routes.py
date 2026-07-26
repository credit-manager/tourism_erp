import datetime
from fastapi import Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from currency_utils import D, DECIMAL_ZERO

from models import UmrahPackage, Employee, Currency, generate_umrah_number
from . import templates, get_db
import auth


def setup_umrah_routes(app):
    @app.get("/umrah", response_class=HTMLResponse)
    def umrah_page(request: Request, db: Session = Depends(get_db),
                   user=Depends(auth.require_permission("umrah.view"))):
        packages = db.query(UmrahPackage).order_by(UmrahPackage.id.desc()).all()
        employees = db.query(Employee).all()
        currencies = db.query(Currency).all()
        return templates.TemplateResponse(request, "umrah.html", {
            "request": request, "page_title": "العمرة (Umrah)", "active": "umrah",
            "packages": packages, "employees": employees, "currencies": currencies,
        })

    @app.post("/umrah/add")
    def add_umrah(pilgrim_name: str = Form(...), passport_no: str = Form(""), phone: str = Form(""),
                  departure_date: str = Form(None), return_date: str = Form(None),
                  hotel_makkah: str = Form(""), hotel_madinah: str = Form(""),
                  cost_price: float = Form(0), sale_price: float = Form(0), paid_amount: float = Form(0),
                  currency_id: int = Form(None), exchange_rate: float = Form(1),
                  employee_id: int = Form(None), notes: str = Form(""), db: Session = Depends(get_db),
                  user=Depends(auth.require_permission("umrah.manage"))):
        def parse_date(s):
            try: return datetime.datetime.strptime(s, "%Y-%m-%d").date()
            except Exception: return None
        cost_d = D(cost_price)
        rate = D(exchange_rate)
        db.add(UmrahPackage(package_number=generate_umrah_number(db), created_date=datetime.date.today(),
                            pilgrim_name=pilgrim_name, passport_no=passport_no, phone=phone,
                            departure_date=parse_date(departure_date), return_date=parse_date(return_date),
                            hotel_makkah=hotel_makkah, hotel_madinah=hotel_madinah,
                            cost_price=cost_d, sale_price=D(sale_price), paid_amount=D(paid_amount),
                            currency_id=currency_id or None, exchange_rate=rate,
                            amount_currency=cost_d, amount_base=cost_d * rate,
                            employee_id=employee_id or None, notes=notes))
        db.commit()
        return RedirectResponse("/umrah", status_code=303)

    @app.post("/umrah/{package_id}/edit")
    def edit_umrah(package_id: int, pilgrim_name: str = Form(...), passport_no: str = Form(""),
                   phone: str = Form(""), departure_date: str = Form(None), return_date: str = Form(None),
                   hotel_makkah: str = Form(""), hotel_madinah: str = Form(""),
                   cost_price: float = Form(0), sale_price: float = Form(0), paid_amount: float = Form(0),
                   currency_id: int = Form(None), exchange_rate: float = Form(1),
                   employee_id: int = Form(None), notes: str = Form(""), db: Session = Depends(get_db),
                   user=Depends(auth.require_permission("umrah.manage"))):
        def parse_date(s):
            try: return datetime.datetime.strptime(s, "%Y-%m-%d").date()
            except Exception: return None
        p = db.query(UmrahPackage).get(package_id)
        if p:
            cost_d = D(cost_price)
            rate = D(exchange_rate)
            p.pilgrim_name, p.passport_no, p.phone = pilgrim_name, passport_no, phone
            p.departure_date, p.return_date = parse_date(departure_date), parse_date(return_date)
            p.hotel_makkah, p.hotel_madinah = hotel_makkah, hotel_madinah
            p.cost_price, p.sale_price, p.paid_amount = cost_d, D(sale_price), D(paid_amount)
            p.currency_id, p.exchange_rate = currency_id or None, rate
            p.amount_currency, p.amount_base = cost_d, cost_d * rate
            p.employee_id, p.notes = employee_id or None, notes
            db.commit()
        return RedirectResponse("/umrah", status_code=303)

    @app.post("/umrah/{package_id}/delete")
    def delete_umrah(package_id: int, db: Session = Depends(get_db),
                     user=Depends(auth.require_permission("umrah.manage"))):
        p = db.query(UmrahPackage).get(package_id)
        if p:
            db.delete(p)
            db.commit()
        return RedirectResponse("/umrah", status_code=303)
