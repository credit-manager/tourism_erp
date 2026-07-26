from fastapi import Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import func
from currency_utils import D, DECIMAL_ZERO
import datetime, json, urllib.parse

from models import Customer, Hotel, Service, Transport, Ticket, Employee, Reservation, Quotation, QuotationLineItem, QuotationVersion, generate_booking_number
from . import templates, get_db
import auth

QUOTATION_TYPES = ["hotel", "transport", "visa", "ticket", "insurance", "trip", "service", "other"]


def generate_quote_number(db: Session) -> str:
    today = datetime.date.today()
    prefix = f"Q-{today.strftime('%Y%m%d')}-"
    last = db.query(func.max(Quotation.id)).scalar() or 0
    return f"{prefix}{last + 1:04d}"


def setup_quotation_routes(app):
    @app.get("/quotations", response_class=HTMLResponse)
    def quotations_list(request: Request, db: Session = Depends(get_db)):
        qs = db.query(Quotation).order_by(Quotation.id.desc()).all()
        return templates.TemplateResponse(request, "quotations.html", {
            "request": request, "quotations": qs, "page_title": "عروض الأسعار",
            "active": "quotations",
        })

    @app.get("/quotations/add", response_class=HTMLResponse)
    def add_quotation_page(request: Request, db: Session = Depends(get_db)):
        customers = db.query(Customer).order_by(Customer.name).all()
        hotels = db.query(Hotel).order_by(Hotel.name).all()
        services = db.query(Service).order_by(Service.name).all()
        transports = db.query(Transport).order_by(Transport.id.desc()).all() if hasattr(Transport, 'id') else []
        return templates.TemplateResponse(request, "quotation_form.html", {
            "request": request, "customers": customers, "hotels": hotels,
            "services": services, "transports": transports,
            "page_title": "إنشاء عرض سعر", "active": "quotations", "edit": False,
        })

    @app.post("/quotations/add")
    def add_quotation(customer_id: int = Form(...), validity_date: str = Form(""),
                      discount_type: str = Form("fixed"), discount_value: str = Form("0"),
                      tax_percentage: str = Form("0"), profit_margin: str = Form("0"),
                      notes: str = Form(""), terms_conditions: str = Form(""),
                      items_json: str = Form("[]"),
                      db: Session = Depends(get_db),
                      user=Depends(auth.require_permission("customers.manage"))):
        qn = generate_quote_number(db)
        vd = None
        if validity_date:
            try:
                vd = datetime.date.fromisoformat(validity_date)
            except ValueError:
                pass
        q = Quotation(quote_number=qn, customer_id=customer_id, validity_date=vd,
                      discount_type=discount_type, discount_value=D(discount_value),
                      tax_percentage=D(tax_percentage), profit_margin=D(profit_margin),
                      notes=notes, terms_conditions=terms_conditions,
                      created_by=user.username if hasattr(user, 'username') else 'admin')
        items_data = json.loads(items_json)
        sub = DECIMAL_ZERO
        for it in items_data:
            sp = D(it.get("sale_price", "0"))
            qty = int(it.get("qty", 1))
            tot = sp * qty
            sub += tot
            q.items.append(QuotationLineItem(
                item_type=it.get("item_type", "other"),
                description=it.get("description", ""),
                item_data=json.dumps(it.get("item_data", {})),
                cost_price=D(it.get("cost_price", "0")),
                sale_price=sp, qty=qty, total=tot,
            ))
        q.subtotal = sub
        disc = D(discount_value)
        if discount_type == "percentage":
            disc = sub * disc / D(100)
        after_disc = sub - disc
        tax = after_disc * D(tax_percentage) / D(100)
        q.tax_amount = tax
        q.grand_total = after_disc + tax
        db.add(q)
        db.commit()
        return RedirectResponse(f"/quotations/{q.id}", status_code=303)

    @app.get("/quotations/{qid}", response_class=HTMLResponse)
    def view_quotation(qid: int, request: Request, db: Session = Depends(get_db)):
        q = db.query(Quotation).get(qid)
        if not q:
            return RedirectResponse("/quotations", status_code=303)
        return templates.TemplateResponse(request, "quotation_view.html", {
            "request": request, "q": q, "page_title": f"عرض سعر {q.quote_number}",
            "active": "quotations",
        })

    @app.post("/quotations/{qid}/status")
    def update_quotation_status(qid: int, status: str = Form(...),
                                db: Session = Depends(get_db),
                                user=Depends(auth.require_permission("customers.manage"))):
        q = db.query(Quotation).get(qid)
        if q:
            q.status = status
            db.commit()
        return RedirectResponse(f"/quotations/{qid}", status_code=303)

    @app.post("/quotations/{qid}/version")
    def create_version(qid: int, db: Session = Depends(get_db),
                       user=Depends(auth.require_permission("customers.manage"))):
        q = db.query(Quotation).get(qid)
        if not q:
            return JSONResponse({"ok": False}, status_code=404)
        q.version += 1
        snapshot = {
            "items": [{"item_type": i.item_type, "description": i.description,
                        "cost_price": float(i.cost_price or 0), "sale_price": float(i.sale_price or 0),
                        "qty": i.qty, "total": float(i.total or 0)} for i in q.items],
            "subtotal": float(q.subtotal or 0), "discount_value": float(q.discount_value or 0),
            "tax_amount": float(q.tax_amount or 0), "grand_total": float(q.grand_total or 0),
        }
        db.add(QuotationVersion(quotation_id=qid, version=q.version,
                                 snapshot=json.dumps(snapshot)))
        db.commit()
        return RedirectResponse(f"/quotations/{qid}", status_code=303)

    @app.post("/quotations/{qid}/accept")
    def accept_quotation(qid: int, db: Session = Depends(get_db),
                         user=Depends(auth.require_permission("customers.manage"))):
        q = db.query(Quotation).get(qid)
        if not q or q.status == "accepted" or q.reservation_id:
            return RedirectResponse(f"/quotations/{qid}", status_code=303)
        # Build reservation from quotation items
        hotel_item = None
        total_sale = DECIMAL_ZERO
        transport_cost = DECIMAL_ZERO
        excursions_cost = DECIMAL_ZERO
        visa_cost = DECIMAL_ZERO
        insurance_cost = DECIMAL_ZERO
        other_cost = DECIMAL_ZERO
        room_type = ""
        meal_plan = ""
        room_count = 1
        checkin = None
        checkout = None
        extra_services = []

        for it in q.items:
            total_sale += D(it.sale_price or 0) * D(it.qty or 1)
            data = {}
            if it.item_data:
                try:
                    data = json.loads(it.item_data)
                except (json.JSONDecodeError, TypeError):
                    pass
            if it.item_type == "hotel":
                hotel_item = it
                room_type = data.get("room_type", "")
                meal_plan = data.get("meal_plan", "")
                room_count = int(data.get("room_count", 1))
                if data.get("checkin_date"):
                    try:
                        checkin = datetime.date.fromisoformat(data["checkin_date"])
                    except ValueError:
                        pass
                if data.get("checkout_date"):
                    try:
                        checkout = datetime.date.fromisoformat(data["checkout_date"])
                    except ValueError:
                        pass
            elif it.item_type == "transport":
                transport_cost += D(it.sale_price or 0) * D(it.qty or 1)
            elif it.item_type == "trip":
                excursions_cost += D(it.sale_price or 0) * D(it.qty or 1)
            elif it.item_type == "visa":
                visa_cost += D(it.sale_price or 0) * D(it.qty or 1)
            elif it.item_type == "insurance":
                insurance_cost += D(it.sale_price or 0) * D(it.qty or 1)
            elif it.item_type == "service":
                extra_services.append(it)

        cust = db.query(Customer).get(q.customer_id)
        guest = cust.name if cust else ""
        hotel_id = None
        if hotel_item and hotel_item.item_data:
            try:
                hdata = json.loads(hotel_item.item_data)
                hotel_id = int(hdata.get("hotel_id", 0)) or None
            except (json.JSONDecodeError, TypeError, ValueError):
                pass

        disc = DECIMAL_ZERO
        if q.discount_value:
            if q.discount_type == "percentage":
                disc = total_sale * D(q.discount_value) / D(100)
            else:
                disc = D(q.discount_value)
        tax_amt = (total_sale - disc) * D(q.tax_percentage or 0) / D(100)

        # Generate a unique booking number from the quote
        bn = f"QTE-{q.quote_number}-{datetime.datetime.now().strftime('%H%M%S')}"
        res = Reservation(
            booking_number=bn,
            customer_id=q.customer_id,
            guest_name=guest,
            hotel_id=hotel_id,
            room_type=room_type,
            meal_plan=meal_plan,
            room_count=room_count,
            stay_type=meal_plan,
            checkin_date=checkin,
            checkout_date=checkout,
            company_cost=total_sale,
            discount=disc,
            taxes=tax_amt,
            transportation_cost=transport_cost,
            excursions_cost=excursions_cost,
            visa_cost=visa_cost,
            insurance_cost=insurance_cost,
            other_services_cost=other_cost,
            status="confirmed",
            adults=1,
        )
        db.add(res)
        db.flush()

        # Link services
        for svc in extra_services:
            if svc.item_data:
                try:
                    sd = json.loads(svc.item_data)
                    sid = sd.get("service_id")
                    if sid:
                        s = db.query(Service).get(int(sid))
                        if s:
                            res.services.append(s)
                except (json.JSONDecodeError, TypeError, ValueError):
                    pass

        q.status = "accepted"
        q.reservation_id = res.id
        db.commit()
        return RedirectResponse(f"/reservations/{res.id}/edit", status_code=303)

    @app.get("/quotations/{qid}/pdf", response_class=HTMLResponse)
    def view_quotation_pdf(qid: int, request: Request, db: Session = Depends(get_db)):
        q = db.query(Quotation).get(qid)
        if not q:
            return RedirectResponse("/quotations", status_code=303)
        return templates.TemplateResponse(request, "quotation_pdf.html", {
            "request": request, "q": q,
        })

    @app.get("/quotations/{qid}/send")
    def send_quotation(qid: int, method: str = "email", db: Session = Depends(get_db)):
        q = db.query(Quotation).get(qid)
        if not q:
            return JSONResponse({"ok": False}, status_code=404)
        subject = f"Quote {q.quote_number}"
        body = f"Quotation {q.quote_number}\nTotal: {q.grand_total}\n\nView: http://localhost:8000/quotations/{q.id}"
        if method == "email":
            email = q.customer.email if q.customer and q.customer.email else ""
            mailto = f"mailto:{email}?subject={urllib.parse.quote(subject)}&body={urllib.parse.quote(body)}"
            return RedirectResponse(mailto, status_code=303)
        elif method == "whatsapp":
            phone = q.customer.phone if q.customer and q.customer.phone else ""
            if phone:
                phone = phone.replace("+", "").replace(" ", "").replace("-", "")
                wa = f"https://wa.me/{phone}?text={urllib.parse.quote(body)}"
                return RedirectResponse(wa, status_code=303)
            return JSONResponse({"ok": False, "error": "No phone on file"})
        return JSONResponse({"ok": False}, status_code=400)

    @app.get("/quotations/{qid}/print")
    def print_quotation(qid: int, request: Request, db: Session = Depends(get_db)):
        q = db.query(Quotation).get(qid)
        if not q:
            return RedirectResponse("/quotations", status_code=303)
        # Duplicate the view template but with print layout
        return templates.TemplateResponse(request, "quotation_pdf.html", {
            "request": request, "q": q, "print_mode": True,
        })
