import datetime
from fastapi import Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy import desc
from currency_utils import D, DECIMAL_ZERO

from models import CommissionPolicy, CommissionEntry, Currency, Reservation
from . import templates, get_db
import auth


def setup_commission_policy_routes(app):
    @app.get("/settings/commission-policies", response_class=HTMLResponse)
    def commission_policies_page(request: Request, db: Session = Depends(get_db),
                                 user=Depends(auth.require_permission("settings.manage"))):
        policies = db.query(CommissionPolicy).order_by(CommissionPolicy.id.desc()).all()
        return templates.TemplateResponse(request, "commission_policies.html", {
            "request": request, "page_title": "سياسات العمولات", "active": "settings",
            "policies": policies,
        })

    @app.get("/settings/commission-policies/add", response_class=HTMLResponse)
    def add_commission_policy_page(request: Request, db: Session = Depends(get_db),
                                   user=Depends(auth.require_permission("settings.manage"))):
        return templates.TemplateResponse(request, "commission_policy_form.html", {
            "request": request, "page_title": "إضافة سياسة عمولة", "active": "settings",
            "policy": None,
        })

    @app.post("/settings/commission-policies/add")
    def add_commission_policy(
        name: str = Form(...),
        commission_base: str = Form("profit"),
        eligibility: str = Form("on_booking"),
        role: str = Form("reservation_rep"),
        rate_type: str = Form("percentage"),
        rate_value: float = Form(0),
        min_amount: float = Form(0),
        max_amount: float = Form(0),
        valid_from: str = Form(None),
        valid_until: str = Form(None),
        cancellation_effect: str = Form("forfeit"),
        applies_to: str = Form(""),
        is_active: int = Form(1),
        db: Session = Depends(get_db),
        user=Depends(auth.require_permission("settings.manage")),
    ):
        def parse_date(s):
            try: return datetime.datetime.strptime(s, "%Y-%m-%d").date()
            except Exception: return None
        db.add(CommissionPolicy(
            name=name, commission_base=commission_base, eligibility=eligibility,
            role=role, rate_type=rate_type, rate_value=D(rate_value),
            min_amount=D(min_amount), max_amount=D(max_amount),
            valid_from=parse_date(valid_from), valid_until=parse_date(valid_until),
            cancellation_effect=cancellation_effect, applies_to=applies_to,
            is_active=is_active,
        ))
        db.commit()
        return RedirectResponse("/settings/commission-policies?success=added", status_code=303)

    @app.get("/settings/commission-policies/{policy_id}/edit", response_class=HTMLResponse)
    def edit_commission_policy_page(policy_id: int, request: Request, db: Session = Depends(get_db),
                                    user=Depends(auth.require_permission("settings.manage"))):
        policy = db.query(CommissionPolicy).get(policy_id)
        if not policy:
            return RedirectResponse("/settings/commission-policies?error=not_found", status_code=303)
        return templates.TemplateResponse(request, "commission_policy_form.html", {
            "request": request, "page_title": "تعديل سياسة عمولة", "active": "settings",
            "policy": policy,
        })

    @app.post("/settings/commission-policies/{policy_id}/edit")
    def edit_commission_policy(
        policy_id: int,
        name: str = Form(...),
        commission_base: str = Form("profit"),
        eligibility: str = Form("on_booking"),
        role: str = Form("reservation_rep"),
        rate_type: str = Form("percentage"),
        rate_value: float = Form(0),
        min_amount: float = Form(0),
        max_amount: float = Form(0),
        valid_from: str = Form(None),
        valid_until: str = Form(None),
        cancellation_effect: str = Form("forfeit"),
        applies_to: str = Form(""),
        is_active: int = Form(1),
        db: Session = Depends(get_db),
        user=Depends(auth.require_permission("settings.manage")),
    ):
        def parse_date(s):
            try: return datetime.datetime.strptime(s, "%Y-%m-%d").date()
            except Exception: return None
        p = db.query(CommissionPolicy).get(policy_id)
        if p:
            p.name = name
            p.commission_base = commission_base
            p.eligibility = eligibility
            p.role = role
            p.rate_type = rate_type
            p.rate_value = D(rate_value)
            p.min_amount = D(min_amount)
            p.max_amount = D(max_amount)
            p.valid_from = parse_date(valid_from)
            p.valid_until = parse_date(valid_until)
            p.cancellation_effect = cancellation_effect
            p.applies_to = applies_to
            p.is_active = is_active
            p.updated_at = datetime.datetime.utcnow()
            db.commit()
        return RedirectResponse("/settings/commission-policies?success=edited", status_code=303)

    @app.post("/settings/commission-policies/{policy_id}/delete")
    def delete_commission_policy(policy_id: int, db: Session = Depends(get_db),
                                 user=Depends(auth.require_permission("settings.manage"))):
        p = db.query(CommissionPolicy).get(policy_id)
        if p:
            db.delete(p)
            db.commit()
        return RedirectResponse("/settings/commission-policies?success=deleted", status_code=303)

    @app.post("/settings/commission-policies/{policy_id}/toggle")
    def toggle_commission_policy(policy_id: int, db: Session = Depends(get_db),
                                 user=Depends(auth.require_permission("settings.manage"))):
        p = db.query(CommissionPolicy).get(policy_id)
        if p:
            p.is_active = 0 if p.is_active else 1
            p.updated_at = datetime.datetime.utcnow()
            db.commit()
        return RedirectResponse("/settings/commission-policies", status_code=303)

    @app.get("/settings/commission-policies/entries", response_class=HTMLResponse)
    def commission_entries_page(request: Request, db: Session = Depends(get_db),
                                user=Depends(auth.require_permission("settings.manage"))):
        from models import TreasuryAccount
        entries = db.query(CommissionEntry).order_by(desc(CommissionEntry.id)).limit(200).all()
        accounts = db.query(TreasuryAccount).all()
        return templates.TemplateResponse(request, "commission_entries.html", {
            "request": request, "page_title": "سجلات العمولات", "active": "commission_entries",
            "entries": entries, "accounts": accounts,
        })

    @app.post("/settings/commission-policies/entries/{entry_id}/status")
    def update_entry_status(entry_id: int, status: str = Form(...),
                            db: Session = Depends(get_db),
                            user=Depends(auth.require_permission("settings.manage"))):
        from services.commission_service import CommissionService
        CommissionService(db).update_entry_status(entry_id, status)
        db.commit()
        return RedirectResponse("/settings/commission-policies/entries", status_code=303)

    @app.post("/settings/commission-policies/entries/{entry_id}/pay")
    def pay_commission_entry(entry_id: int, account_id: int = Form(...),
                             db: Session = Depends(get_db),
                             user=Depends(auth.require_permission("settings.manage"))):
        from services.commission_service import CommissionService
        from services.treasury_service import InsufficientBalanceError, AccountNotSelectedError
        try:
            CommissionService(db).pay_entry(entry_id, account_id, created_by=user.username)
            db.commit()
            return RedirectResponse("/settings/commission-policies/entries?success=paid", status_code=303)
        except (InsufficientBalanceError, AccountNotSelectedError, ValueError) as e:
            db.rollback()
            return RedirectResponse(f"/settings/commission-policies/entries?error={e}", status_code=303)
