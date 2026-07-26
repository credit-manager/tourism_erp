import datetime
from fastapi import Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from currency_utils import D, DECIMAL_ZERO

from models import Reservation, Collection, CollectionAllocation, generate_collection_number, TreasuryAccount, Customer, Currency
from . import paginate, pagination_ctx
from . import templates, get_db
import auth


def setup_collection_routes(app):
    @app.get("/collections", response_class=HTMLResponse)
    def collections_page(request: Request, db: Session = Depends(get_db),
                         page: int = 1,
                         user=Depends(auth.require_permission("collections.manage"))):
        collections, pg, tp, tt = paginate(db.query(Collection).order_by(Collection.id.desc()), page)
        open_reservations = [r for r in db.query(Reservation).order_by(Reservation.id.desc()).all() if not r.is_paid_in_full]
        customers = db.query(Customer).all()
        accounts = db.query(TreasuryAccount).all()
        currencies = db.query(Currency).all()
        return templates.TemplateResponse(request, "collections.html", {
            "request": request, "page_title": "التحصيلات (Collections)", "active": "collections",
            "collections": collections, "open_reservations": open_reservations, "customers": customers,
            "accounts": accounts, "currencies": currencies,
            "p": pagination_ctx(pg, tp, tt), "base_url": f"/collections?page={pg}",
        })

    @app.post("/collections/add")
    async def add_collection(request: Request, db: Session = Depends(get_db),
                             user=Depends(auth.require_permission("collections.manage"))):
        form = await request.form()
        from services.collection_service import CollectionService
        svc = CollectionService(db, user)
        data = {
            "payer_name": form.get("payer_name"),
            "total_amount": form.get("total_amount"),
            "notes": form.get("notes"),
            "payment_method": form.get("payment_method", "cash"),
            "allocation_mode": form.get("allocation_mode", "auto"),
            "customer_id": form.get("customer_id"),
            "reservation_ids": [int(x) for x in form.getlist("reservation_ids")],
            "account_id": form.get("account_id"),
            "currency_id": form.get("currency_id"),
            "exchange_rate": form.get("exchange_rate", 1),
            "amount_currency": form.get("amount_currency"),
        }
        for rid in form.getlist("reservation_ids"):
            raw = form.get(f"allocation_amount_{rid}")
            if raw:
                data[f"allocation_amount_{rid}"] = raw
        try:
            svc.create(data)
            db.commit()
        except Exception:
            db.rollback()
            raise
        return RedirectResponse("/collections", status_code=303)
    
    @app.post("/collections/{collection_id}/allocate-remaining")
    async def allocate_remaining_collection(collection_id: int, request: Request, db: Session = Depends(get_db),
                                            user=Depends(auth.require_permission("collections.manage"))):
        from services.collection_service import CollectionService
        svc = CollectionService(db, user)
        form = await request.form()
        reservation_ids = [int(x) for x in form.getlist("reservation_ids")]
        amount = form.get("amount")
        try:
            svc.allocate_remaining(collection_id, reservation_ids,
                                   D(amount) if amount else None)
            db.commit()
        except Exception:
            db.rollback()
            raise
        return RedirectResponse("/collections", status_code=303)

    # ??? Workflow transitions ???
    @app.post("/collections/{collection_id}/submit")
    def submit_collection(collection_id: int, db: Session = Depends(get_db),
                          user=Depends(auth.require_permission("collections.create"))):
        coll = db.query(Collection).get(collection_id)
        if not coll: return RedirectResponse("/collections", status_code=303)
        from services.workflow_service import WorkflowService
        WorkflowService(db).submit(coll, user)
        db.commit()
        return RedirectResponse("/collections", status_code=303)

    @app.post("/collections/{collection_id}/approve")
    def approve_collection(collection_id: int, db: Session = Depends(get_db),
                           user=Depends(auth.require_permission("collections.approve"))):
        coll = db.query(Collection).get(collection_id)
        if not coll: return RedirectResponse("/collections", status_code=303)
        from services.workflow_service import WorkflowService, WorkflowError
        try:
            WorkflowService(db).review(coll, user, approved=True)
            db.commit()
            from services.notification_service import NotificationService
            NotificationService(db).notify_permission(
                "collections.post",
                title=f"تحصيل جاهز للترحيل: {coll.collection_number}",
                body=f"{coll.payer_name} — {coll.total_amount}",
                link="/collections", category="info",
                exclude_user_id=getattr(user, "id", None),
            )
            db.commit()
        except WorkflowError:
            db.rollback()
            return RedirectResponse("/collections?error=workflow_error", status_code=303)
        return RedirectResponse("/collections", status_code=303)

    @app.post("/collections/{collection_id}/post")
    def post_collection(collection_id: int, db: Session = Depends(get_db),
                        user=Depends(auth.require_permission("collections.post"))):
        from services.collection_service import CollectionService
        try:
            CollectionService(db, user).post(collection_id)
            db.commit()
        except Exception as e:
            db.rollback()
            return RedirectResponse(f"/collections?error={e}", status_code=303)
        return RedirectResponse("/collections", status_code=303)

    @app.post("/collections/{collection_id}/cancel")
    def cancel_collection(collection_id: int, db: Session = Depends(get_db),
                          user=Depends(auth.require_permission("collections.cancel"))):
        coll = db.query(Collection).get(collection_id)
        if not coll: return RedirectResponse("/collections", status_code=303)
        from services.workflow_service import WorkflowService
        WorkflowService(db).cancel(coll, user)
        db.commit()
        return RedirectResponse("/collections", status_code=303)

