import datetime
from fastapi import Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from currency_utils import D, DECIMAL_ZERO

from models import Supplier, SupplierPayment, TreasuryAccount, Reservation, Currency
from . import templates, get_db
import auth


def setup_supplier_payment_routes(app):
    @app.get("/suppliers/payments", response_class=HTMLResponse)
    def supplier_payments_page(request: Request, db: Session = Depends(get_db),
                               user=Depends(auth.require_permission("collections.manage"))):
        suppliers = db.query(Supplier).order_by(Supplier.name).all()
        payments = db.query(SupplierPayment).order_by(SupplierPayment.id.desc()).all()
        pending_by_supplier = {}
        for s in suppliers:
            hotel_ids = [h.id for h in (s.hotels or [])]
            reservations = db.query(Reservation).filter(Reservation.hotel_id.in_(hotel_ids)).all() if hotel_ids else []
            pending_by_supplier[s.id] = [r for r in reservations if r.remaining_to_hotel > 0]
        accounts = db.query(TreasuryAccount).all()
        currencies = db.query(Currency).all()
        return templates.TemplateResponse(request, "supplier_payments.html", {
            "request": request, "page_title": "سداد الموردين والفنادق", "active": "supplier_payments",
            "suppliers": suppliers, "payments": payments, "pending_by_supplier": pending_by_supplier,
            "accounts": accounts, "currencies": currencies,
        })

    @app.post("/suppliers/payments/add")
    async def add_supplier_payment(request: Request, db: Session = Depends(get_db),
                                   user=Depends(auth.require_permission("collections.manage"))):
        form = await request.form()
        from services.supplier_payment_service import SupplierPaymentService
        data = {
            "supplier_id": form.get("supplier_id"),
            "total_amount": form.get("total_amount"),
            "notes": form.get("notes", ""),
            "reservation_ids": [int(x) for x in form.getlist("reservation_ids")],
            "account_id": form.get("account_id"),
            "currency_id": form.get("currency_id"),
            "exchange_rate": form.get("exchange_rate", 1),
            "amount_currency": form.get("amount_currency"),
        }
        SupplierPaymentService(db, user).create(data)
        db.commit()
        return RedirectResponse("/suppliers/payments", status_code=303)

    @app.post("/suppliers/payments/{payment_id}/allocate-remaining")
    async def allocate_remaining_supplier_payment(payment_id: int, request: Request, db: Session = Depends(get_db),
                                                  user=Depends(auth.require_permission("collections.manage"))):
        from services.supplier_payment_service import SupplierPaymentService
        form = await request.form()
        reservation_ids = [int(x) for x in form.getlist("reservation_ids")]
        amount = form.get("amount")
        SupplierPaymentService(db, user).allocate_remaining(
            payment_id, reservation_ids, D(amount) if amount else None)
        db.commit()
        return RedirectResponse("/suppliers/payments", status_code=303)

    @app.get("/suppliers/payments/{payment_id}", response_class=HTMLResponse)
    def supplier_payment_view(payment_id: int, request: Request, db: Session = Depends(get_db),
                              user=Depends(auth.require_permission("collections.manage"))):
        payment = db.query(SupplierPayment).get(payment_id)
        if not payment:
            return RedirectResponse("/suppliers/payments", status_code=303)
        return templates.TemplateResponse(request, "supplier_payment_view.html", {
            "active": "supplier_payments",
            "page_title": "دفعة مورد",
            "payment": payment,
        })

    # ??? Workflow transitions ???
    @app.post("/suppliers/payments/{payment_id}/submit")
    def submit_supplier_payment(payment_id: int, db: Session = Depends(get_db),
                                user=Depends(auth.require_permission("supplier_payments.create"))):
        p = db.query(SupplierPayment).get(payment_id)
        if not p: return RedirectResponse("/suppliers/payments", status_code=303)
        from services.workflow_service import WorkflowService
        WorkflowService(db).submit(p, user)
        db.commit()
        return RedirectResponse("/suppliers/payments", status_code=303)

    @app.post("/suppliers/payments/{payment_id}/approve")
    def approve_supplier_payment(payment_id: int, db: Session = Depends(get_db),
                                 user=Depends(auth.require_permission("supplier_payments.approve"))):
        p = db.query(SupplierPayment).get(payment_id)
        if not p: return RedirectResponse("/suppliers/payments", status_code=303)
        if not auth.has_permission(user, "bypass_invoice_approval"):
            unapproved = db.query(SupplierInvoice).filter(
                SupplierInvoice.supplier_id == p.supplier_id,
                SupplierInvoice.status.in_(["draft", "submitted"]),
            ).count()
            if unapproved > 0:
                return RedirectResponse(
                    f"/suppliers/payments?error=يوجد {unapproved} فاتورة مورد غير معتمدة لهذا المورد. يجب اعتمادها أولاً إلا بتصريح تجاوز.",
                    status_code=303)
        from services.workflow_service import WorkflowService, WorkflowError
        try:
            WorkflowService(db).review(p, user, approved=True)
        except WorkflowError as e:
            db.rollback()
            return RedirectResponse(f"/suppliers/payments?error={e}", status_code=303)
        from services.notification_service import NotificationService
        NotificationService(db).notify_permission(
            "supplier_payments.post",
            title=f"دفعة مورد جاهزة للترحيل: {p.payment_number}",
            body=f"{p.supplier.name if p.supplier else ''} — {p.total_amount}",
            link="/suppliers/payments", category="info",
            exclude_user_id=getattr(user, "id", None),
        )
        db.commit()
        return RedirectResponse("/suppliers/payments", status_code=303)

    @app.post("/suppliers/payments/{payment_id}/post")
    def post_supplier_payment(payment_id: int, db: Session = Depends(get_db),
                              user=Depends(auth.require_permission("supplier_payments.post"))):
        from services.supplier_payment_service import SupplierPaymentService
        try:
            SupplierPaymentService(db, user).post(payment_id)
            db.commit()
        except Exception as e:
            return RedirectResponse(f"/suppliers/payments?error={e}", status_code=303)

        from services.insights_service import InsightsService
        from services.notification_service import NotificationService
        dups = [d for d in InsightsService(db).detect_duplicate_supplier_payments()
                if d["a_id"] == payment_id or d["b_id"] == payment_id]
        if dups:
            p = db.query(SupplierPayment).get(payment_id)
            NotificationService(db).notify_permission(
                "supplier_payments.approve",
                title="⚠️ اشتباه دفعة مورد مكررة",
                body=f"{p.payment_number if p else payment_id} — راجعها في صفحة التحليلات",
                link="/insights", category="warning",
            )
            db.commit()
        return RedirectResponse("/suppliers/payments", status_code=303)

    @app.post("/suppliers/payments/{payment_id}/cancel")
    def cancel_supplier_payment(payment_id: int, db: Session = Depends(get_db),
                                user=Depends(auth.require_permission("supplier_payments.cancel"))):
        p = db.query(SupplierPayment).get(payment_id)
        if not p: return RedirectResponse("/suppliers/payments", status_code=303)
        from services.workflow_service import WorkflowService
        WorkflowService(db).cancel(p, user)
        db.commit()
        return RedirectResponse("/suppliers/payments", status_code=303)

