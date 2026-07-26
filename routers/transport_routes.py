import datetime
from fastapi import Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from currency_utils import D, DECIMAL_ZERO

from models import Transport, Supplier, Currency
from . import templates, get_db
import auth


def setup_transport_routes(app):
    @app.get("/transportations", response_class=HTMLResponse)
    def transport_page(request: Request, db: Session = Depends(get_db),
                       user=Depends(auth.require_permission("transport.view"))):
        transports = db.query(Transport).order_by(Transport.id.desc()).all()
        suppliers = db.query(Supplier).all()
        currencies = db.query(Currency).all()
        return templates.TemplateResponse(request, "transportations.html", {
            "request": request, "page_title": "النقل (Transportations)", "active": "transport",
            "transports": transports, "suppliers": suppliers, "currencies": currencies,
        })

    @app.post("/transportations/add")
    def add_transport(vehicle_type: str = Form(...), plate_number: str = Form(""),
                      driver_name: str = Form(""), driver_phone: str = Form(""), capacity: int = Form(0),
                      supplier_id: int = Form(None), trip_date: str = Form(None), route: str = Form(""),
                      cost: float = Form(0), sale_price: float = Form(0),
                      currency_id: int = Form(None), exchange_rate: float = Form(1),
                      notes: str = Form(""),
                      db: Session = Depends(get_db), user=Depends(auth.require_permission("transport.manage"))):
        def parse_date(s):
            try: return datetime.datetime.strptime(s, "%Y-%m-%d").date()
            except Exception: return None
        cost_d = D(cost)
        sale_d = D(sale_price)
        rate = D(exchange_rate)
        db.add(Transport(vehicle_type=vehicle_type, plate_number=plate_number, driver_name=driver_name,
                         driver_phone=driver_phone, capacity=capacity, supplier_id=supplier_id or None,
                         trip_date=parse_date(trip_date), route=route, cost=cost_d, sale_price=sale_d,
                         currency_id=currency_id or None, exchange_rate=rate,
                         amount_currency=cost_d, amount_base=cost_d * rate, notes=notes))
        db.commit()
        return RedirectResponse("/transportations", status_code=303)

    @app.post("/transportations/{transport_id}/edit")
    def edit_transport(transport_id: int, vehicle_type: str = Form(...), plate_number: str = Form(""),
                       driver_name: str = Form(""), driver_phone: str = Form(""), capacity: int = Form(0),
                       supplier_id: int = Form(None), trip_date: str = Form(None), route: str = Form(""),
                       cost: float = Form(0), sale_price: float = Form(0),
                       currency_id: int = Form(None), exchange_rate: float = Form(1),
                       notes: str = Form(""),
                       db: Session = Depends(get_db), user=Depends(auth.require_permission("transport.manage"))):
        def parse_date(s):
            try: return datetime.datetime.strptime(s, "%Y-%m-%d").date()
            except Exception: return None
        t = db.query(Transport).get(transport_id)
        if t:
            cost_d = D(cost)
            rate = D(exchange_rate)
            t.vehicle_type, t.plate_number, t.driver_name = vehicle_type, plate_number, driver_name
            t.driver_phone, t.capacity, t.supplier_id = driver_phone, capacity, supplier_id or None
            t.trip_date, t.route, t.cost, t.sale_price = parse_date(trip_date), route, cost_d, D(sale_price)
            t.currency_id, t.exchange_rate = currency_id or None, rate
            t.amount_currency, t.amount_base = cost_d, cost_d * rate
            t.notes = notes
            db.commit()
        return RedirectResponse("/transportations", status_code=303)

    @app.post("/transportations/{transport_id}/delete")
    def delete_transport(transport_id: int, db: Session = Depends(get_db),
                         user=Depends(auth.require_permission("transport.manage"))):
        t = db.query(Transport).get(transport_id)
        if t:
            db.delete(t)
            db.commit()
        return RedirectResponse("/transportations", status_code=303)
