import datetime
from fastapi import Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from currency_utils import D, DECIMAL_ZERO

from models import Ticket, Employee, Currency, generate_ticket_number
from . import templates, get_db
import auth


def setup_ticket_routes(app):
    @app.get("/tickets", response_class=HTMLResponse)
    def tickets_page(request: Request, db: Session = Depends(get_db),
                     user=Depends(auth.require_permission("tickets.view"))):
        tickets = db.query(Ticket).order_by(Ticket.id.desc()).all()
        employees = db.query(Employee).all()
        currencies = db.query(Currency).all()
        return templates.TemplateResponse(request, "tickets.html", {
            "request": request, "page_title": "التذاكر (Tickets)", "active": "tickets",
            "tickets": tickets, "employees": employees, "currencies": currencies,
        })

    @app.post("/tickets/add")
    def add_ticket(passenger_name: str = Form(...), airline: str = Form(""), flight_number: str = Form(""),
                   route: str = Form(""), departure_date: str = Form(None), return_date: str = Form(None),
                   cost_price: float = Form(0), sale_price: float = Form(0),
                   currency_id: int = Form(None), exchange_rate: float = Form(1),
                   employee_id: int = Form(None),
                   notes: str = Form(""), db: Session = Depends(get_db),
                   user=Depends(auth.require_permission("tickets.manage"))):
        def parse_date(s):
            try: return datetime.datetime.strptime(s, "%Y-%m-%d").date()
            except Exception: return None
        cost_d = D(cost_price)
        rate = D(exchange_rate)
        db.add(Ticket(ticket_number=generate_ticket_number(db), created_date=datetime.date.today(),
                      passenger_name=passenger_name, airline=airline, flight_number=flight_number, route=route,
                      departure_date=parse_date(departure_date), return_date=parse_date(return_date),
                      cost_price=cost_d, sale_price=D(sale_price),
                      currency_id=currency_id or None, exchange_rate=rate,
                      amount_currency=cost_d, amount_base=cost_d * rate,
                      employee_id=employee_id or None, status="confirmed", notes=notes))
        db.commit()
        return RedirectResponse("/tickets", status_code=303)

    @app.post("/tickets/{ticket_id}/edit")
    def edit_ticket(ticket_id: int, passenger_name: str = Form(...), airline: str = Form(""),
                    flight_number: str = Form(""), route: str = Form(""),
                    departure_date: str = Form(None), return_date: str = Form(None),
                    cost_price: float = Form(0), sale_price: float = Form(0),
                    currency_id: int = Form(None), exchange_rate: float = Form(1),
                    employee_id: int = Form(None),
                    status: str = Form("confirmed"), notes: str = Form(""),
                    db: Session = Depends(get_db), user=Depends(auth.require_permission("tickets.manage"))):
        def parse_date(s):
            try: return datetime.datetime.strptime(s, "%Y-%m-%d").date()
            except Exception: return None
        t = db.query(Ticket).get(ticket_id)
        if t:
            cost_d = D(cost_price)
            rate = D(exchange_rate)
            t.passenger_name, t.airline, t.flight_number, t.route = passenger_name, airline, flight_number, route
            t.departure_date, t.return_date = parse_date(departure_date), parse_date(return_date)
            t.cost_price, t.sale_price = cost_d, D(sale_price)
            t.currency_id, t.exchange_rate = currency_id or None, rate
            t.amount_currency, t.amount_base = cost_d, cost_d * rate
            t.employee_id = employee_id or None
            t.status, t.notes = status, notes
            db.commit()
        return RedirectResponse("/tickets", status_code=303)

    @app.post("/tickets/{ticket_id}/delete")
    def delete_ticket(ticket_id: int, db: Session = Depends(get_db),
                      user=Depends(auth.require_permission("tickets.manage"))):
        t = db.query(Ticket).get(ticket_id)
        if t:
            db.delete(t)
            db.commit()
        return RedirectResponse("/tickets", status_code=303)
