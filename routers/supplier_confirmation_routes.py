import datetime
from fastapi import Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from currency_utils import D, DECIMAL_ZERO

from models import (
    Supplier, SupplierConfirmation, SupplierConfirmationLine,
    Reservation, Currency, generate_confirmation_number,
)
from . import templates, get_db
import auth


def setup_supplier_confirmation_routes(app):
    @app.get("/suppliers/confirmations", response_class=HTMLResponse)
    def supplier_confirmations_page(request: Request, db: Session = Depends(get_db),
                                    user=Depends(auth.require_permission("supplier_confirmations.view"))):
        confirmations = db.query(SupplierConfirmation).order_by(SupplierConfirmation.id.desc()).all()
        suppliers = db.query(Supplier).all()
        currencies = db.query(Currency).all()
        return templates.TemplateResponse(request, "supplier_confirmations.html", {
            "request": request, "page_title": "تأكيدات الموردين", "active": "supplier_confirmations",
            "confirmations": confirmations, "suppliers": suppliers, "currencies": currencies,
        })

    @app.get("/suppliers/confirmations/add", response_class=HTMLResponse)
    def add_supplier_confirmation_page(request: Request, db: Session = Depends(get_db),
                                       user=Depends(auth.require_permission("supplier_confirmations.manage"))):
        suppliers = db.query(Supplier).all()
        currencies = db.query(Currency).all()
        reservations = db.query(Reservation).filter(
            Reservation.status.in_(["confirmed", "in_house", "checked_out"])
        ).order_by(Reservation.id.desc()).limit(200).all()
        return templates.TemplateResponse(request, "supplier_confirmation_form.html", {
            "request": request, "page_title": "إضافة تأكيد مورد", "active": "supplier_confirmations",
            "suppliers": suppliers, "reservations": reservations, "confirmation": None, "currencies": currencies,
        })

    @app.post("/suppliers/confirmations/add")
    async def add_supplier_confirmation(request: Request, db: Session = Depends(get_db),
                                        user=Depends(auth.require_permission("supplier_confirmations.manage"))):
        form = await request.form()
        supplier_id = int(form.get("supplier_id"))
        confirmation_date = datetime.datetime.strptime(form.get("confirmation_date"), "%Y-%m-%d").date()
        currency_id_str = form.get("currency_id")
        currency_id = int(currency_id_str) if currency_id_str and str(currency_id_str).strip() else None
        exchange_rate = D(form.get("exchange_rate", 1))
        notes = form.get("notes", "")
        conf = SupplierConfirmation(
            confirmation_number=generate_confirmation_number(db),
            supplier_id=supplier_id, confirmation_date=confirmation_date,
            currency_id=currency_id, exchange_rate=exchange_rate,
            notes=notes, status="draft", created_by=user.username,
        )
        db.add(conf)
        db.flush()

        line_index = 0
        while True:
            rid_key = f"lines[{line_index}][reservation_id]"
            if rid_key not in form: break
            reservation_id = int(form.get(rid_key))
            confirmed_cost = D(form.get(f"lines[{line_index}][confirmed_cost]", 0))
            line_notes = form.get(f"lines[{line_index}][notes]", "")
            db.add(SupplierConfirmationLine(
                confirmation_id=conf.id, reservation_id=reservation_id,
                confirmed_cost=confirmed_cost, notes=line_notes,
            ))
            line_index += 1

        total_confirmed = sum(D(form.get(f"lines[{i}][confirmed_cost]", 0)) for i in range(line_index))
        conf.amount_currency = total_confirmed
        conf.amount_base = total_confirmed * conf.exchange_rate
        db.commit()
        return RedirectResponse(f"/suppliers/confirmations?success=added", status_code=303)

    @app.get("/suppliers/confirmations/{conf_id}", response_class=HTMLResponse)
    def view_supplier_confirmation(conf_id: int, request: Request, db: Session = Depends(get_db),
                                   user=Depends(auth.require_permission("supplier_confirmations.view"))):
        conf = db.query(SupplierConfirmation).get(conf_id)
        if not conf:
            return RedirectResponse("/suppliers/confirmations?error=not_found", status_code=303)
        total_expected = DECIMAL_ZERO
        total_confirmed = DECIMAL_ZERO
        try:
            for line in (conf.lines or []):
                cost = D(line.reservation.stay_cost) if line.reservation else DECIMAL_ZERO
                total_expected += cost
                total_confirmed += D(line.confirmed_cost)
        except Exception:
            pass
        total_diff = total_confirmed - total_expected
        return templates.TemplateResponse(request, "supplier_confirmation_view.html", {
            "request": request, "page_title": "عرض تأكيد مورد", "active": "supplier_confirmations",
            "conf": conf,
            "total_expected": total_expected, "total_confirmed": total_confirmed,
            "total_diff": total_diff,
        })

    @app.post("/suppliers/confirmations/{conf_id}/confirm")
    def confirm_supplier_confirmation(conf_id: int, db: Session = Depends(get_db),
                                      user=Depends(auth.require_permission("supplier_confirmations.manage"))):
        conf = db.query(SupplierConfirmation).get(conf_id)
        if not conf:
            return RedirectResponse("/suppliers/confirmations?error=not_found", status_code=303)
        conf.status = "confirmed"
        conf.confirmed_by = user.username
        conf.confirmed_at = datetime.datetime.utcnow()
        db.commit()
        return RedirectResponse(f"/suppliers/confirmations?success=confirmed", status_code=303)

    @app.post("/suppliers/confirmations/{conf_id}/cancel")
    def cancel_supplier_confirmation(conf_id: int, db: Session = Depends(get_db),
                                     user=Depends(auth.require_permission("supplier_confirmations.manage"))):
        conf = db.query(SupplierConfirmation).get(conf_id)
        if not conf:
            return RedirectResponse("/suppliers/confirmations?error=not_found", status_code=303)
        conf.status = "cancelled"
        db.commit()
        return RedirectResponse(f"/suppliers/confirmations?success=cancelled", status_code=303)
