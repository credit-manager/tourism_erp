import datetime
from fastapi import Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy import func
from currency_utils import D, DECIMAL_ZERO

from models import (
    Supplier, SupplierInvoice, SupplierInvoiceLine,
    SupplierConfirmation, SupplierConfirmationLine,
    Reservation, Currency, generate_invoice_number,
)
from . import templates, get_db
import auth


def setup_supplier_invoice_routes(app):
    @app.get("/suppliers/invoices", response_class=HTMLResponse)
    def supplier_invoices_page(request: Request, db: Session = Depends(get_db),
                               user=Depends(auth.require_permission("supplier_invoices.view"))):
        invoices = db.query(SupplierInvoice).order_by(SupplierInvoice.id.desc()).all()
        suppliers = db.query(Supplier).all()
        currencies = db.query(Currency).all()
        return templates.TemplateResponse(request, "supplier_invoices.html", {
            "request": request, "page_title": "فواتير الموردين", "active": "supplier_invoices",
            "invoices": invoices, "suppliers": suppliers, "currencies": currencies,
        })

    @app.get("/suppliers/invoices/add", response_class=HTMLResponse)
    def add_supplier_invoice_page(request: Request, db: Session = Depends(get_db),
                                  user=Depends(auth.require_permission("supplier_invoices.manage"))):
        suppliers = db.query(Supplier).all()
        currencies = db.query(Currency).all()
        confirmations = db.query(SupplierConfirmation).filter(
            SupplierConfirmation.status == "confirmed"
        ).all()
        reservations = db.query(Reservation).filter(
            Reservation.status.in_(["confirmed", "in_house", "checked_out"])
        ).order_by(Reservation.id.desc()).limit(200).all()
        return templates.TemplateResponse(request, "supplier_invoice_form.html", {
            "request": request, "page_title": "إضافة فاتورة مورد", "active": "supplier_invoices",
            "suppliers": suppliers, "confirmations": confirmations,
            "reservations": reservations, "invoice": None, "currencies": currencies,
        })

    @app.post("/suppliers/invoices/add")
    async def add_supplier_invoice(request: Request, db: Session = Depends(get_db),
                                   user=Depends(auth.require_permission("supplier_invoices.manage"))):
        form = await request.form()
        supplier_id = int(form.get("supplier_id"))
        invoice_date = datetime.datetime.strptime(form.get("invoice_date"), "%Y-%m-%d").date()
        due_date = datetime.datetime.strptime(form.get("due_date"), "%Y-%m-%d").date() if form.get("due_date") else None
        reference_number = form.get("reference_number", "")
        currency_id_str = form.get("currency_id")
        currency_id = int(currency_id_str) if currency_id_str and str(currency_id_str).strip() else None
        exchange_rate = D(form.get("exchange_rate", 1))
        notes = form.get("notes", "")
        invoice = SupplierInvoice(
            invoice_number=generate_invoice_number(db),
            supplier_id=supplier_id, invoice_date=invoice_date,
            due_date=due_date, reference_number=reference_number,
            currency_id=currency_id, exchange_rate=exchange_rate,
            total_before_tax=DECIMAL_ZERO, tax_amount=DECIMAL_ZERO,
            discount_amount=DECIMAL_ZERO, total_amount=DECIMAL_ZERO,
            notes=notes, status="draft", created_by=user.username,
        )
        db.add(invoice)
        db.flush()

        total_before_tax = DECIMAL_ZERO
        total_tax = DECIMAL_ZERO
        total_discount = DECIMAL_ZERO
        # حد اقصى 500 سطر
        line_index = 0
        while True:
            rid_key = f"lines[{line_index}][reservation_id]"
            if rid_key not in form: break
            reservation_id = int(form.get(rid_key))
            description = form.get(f"lines[{line_index}][description]", "")
            invoiced_cost = D(form.get(f"lines[{line_index}][invoiced_cost]"))
            tax_amt = D(form.get(f"lines[{line_index}][tax_amount]"))
            discount_amt = D(form.get(f"lines[{line_index}][discount_amount]"))
            confirmed_cost = D(form.get(f"lines[{line_index}][confirmed_cost]", 0))
            confirmation_line_id_str = form.get(f"lines[{line_index}][confirmation_line_id]")
            confirmation_line_id = int(confirmation_line_id_str) if confirmation_line_id_str else None

            reservation = db.query(Reservation).get(reservation_id)
            expected_cost = D(reservation.stay_cost) if reservation else DECIMAL_ZERO
            cost_diff = invoiced_cost - expected_cost
            net_amt = invoiced_cost + tax_amt - discount_amt

            db.add(SupplierInvoiceLine(
                invoice_id=invoice.id, reservation_id=reservation_id,
                confirmation_line_id=confirmation_line_id,
                description=description,
                expected_cost=expected_cost, confirmed_cost=confirmed_cost,
                invoiced_cost=invoiced_cost,
                cost_difference=cost_diff,
                tax_amount=tax_amt, discount_amount=discount_amt,
                net_amount=net_amt, notes="",
            ))
            total_before_tax += invoiced_cost
            total_tax += tax_amt
            total_discount += discount_amt
            line_index += 1

        invoice.total_before_tax = total_before_tax
        invoice.tax_amount = total_tax
        invoice.discount_amount = total_discount
        invoice.total_amount = total_before_tax + total_tax - total_discount
        invoice.amount_currency = invoice.total_amount
        invoice.amount_base = invoice.total_amount * invoice.exchange_rate
        db.commit()
        return RedirectResponse(f"/suppliers/invoices?success=added", status_code=303)

    @app.get("/suppliers/invoices/{invoice_id}", response_class=HTMLResponse)
    def view_supplier_invoice(invoice_id: int, request: Request, db: Session = Depends(get_db),
                              user=Depends(auth.require_permission("supplier_invoices.view"))):
        invoice = db.query(SupplierInvoice).get(invoice_id)
        if not invoice:
            return RedirectResponse("/suppliers/invoices?error=not_found", status_code=303)
        return templates.TemplateResponse(request, "supplier_invoice_view.html", {
            "request": request, "page_title": "عرض فاتورة مورد", "active": "supplier_invoices",
            "inv": invoice,
        })

    @app.post("/suppliers/invoices/{invoice_id}/approve")
    def approve_supplier_invoice(invoice_id: int, db: Session = Depends(get_db),
                                 user=Depends(auth.require_permission("supplier_invoices.approve"))):
        invoice = db.query(SupplierInvoice).get(invoice_id)
        if not invoice:
            return RedirectResponse("/suppliers/invoices?error=not_found", status_code=303)
        invoice.status = "approved"
        invoice.approved_by = user.username
        invoice.approved_at = datetime.datetime.utcnow()
        db.commit()
        return RedirectResponse(f"/suppliers/invoices?success=approved", status_code=303)

    @app.post("/suppliers/invoices/{invoice_id}/cancel")
    def cancel_supplier_invoice(invoice_id: int, db: Session = Depends(get_db),
                                user=Depends(auth.require_permission("supplier_invoices.manage"))):
        invoice = db.query(SupplierInvoice).get(invoice_id)
        if not invoice:
            return RedirectResponse("/suppliers/invoices?error=not_found", status_code=303)
        invoice.status = "cancelled"
        db.commit()
        return RedirectResponse(f"/suppliers/invoices?success=cancelled", status_code=303)

    @app.get("/suppliers/invoices/{invoice_id}/edit", response_class=HTMLResponse)
    def edit_supplier_invoice_page(invoice_id: int, request: Request, db: Session = Depends(get_db),
                                   user=Depends(auth.require_permission("supplier_invoices.manage"))):
        invoice = db.query(SupplierInvoice).get(invoice_id)
        if not invoice:
            return RedirectResponse("/suppliers/invoices?error=not_found", status_code=303)
        suppliers = db.query(Supplier).all()
        currencies = db.query(Currency).all()
        return templates.TemplateResponse(request, "supplier_invoice_form.html", {
            "request": request, "page_title": "تعديل فاتورة مورد", "active": "supplier_invoices",
            "suppliers": suppliers, "invoice": invoice,
            "confirmations": [], "reservations": [], "currencies": currencies,
        })

    # ─── Three-way matching report ───
    @app.get("/suppliers/invoices/{invoice_id}/match", response_class=HTMLResponse)
    def three_way_match(invoice_id: int, request: Request, db: Session = Depends(get_db),
                        user=Depends(auth.require_permission("supplier_invoices.view"))):
        invoice = db.query(SupplierInvoice).get(invoice_id)
        if not invoice:
            return RedirectResponse("/suppliers/invoices?error=not_found", status_code=303)
        match_data = []
        for line in invoice.lines:
            res = line.reservation
            conf_line = line.confirmation_line
            expected = D(line.expected_cost)
            confirmed = D(line.confirmed_cost) if conf_line else DECIMAL_ZERO
            invoiced = D(line.invoiced_cost)
            conf_vs_exp = confirmed - expected
            inv_vs_conf = invoiced - confirmed
            inv_vs_exp = invoiced - expected
            match_data.append({
                "line": line, "reservation": res,
                "confirmation_line": conf_line,
                "expected": expected, "confirmed": confirmed, "invoiced": invoiced,
                "conf_vs_exp": conf_vs_exp, "inv_vs_conf": inv_vs_conf, "inv_vs_exp": inv_vs_exp,
                "status": "match" if (abs(inv_vs_exp) < 0.01) else ("minor_diff" if abs(inv_vs_exp) < 10 else "major_diff"),
            })
        return templates.TemplateResponse(request, "supplier_invoice_match.html", {
            "request": request, "page_title": "المطابقة الثلاثية", "active": "supplier_invoices",
            "inv": invoice, "match_data": match_data,
        })
