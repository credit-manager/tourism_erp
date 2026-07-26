from fastapi import Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy import func
from currency_utils import D, DECIMAL_ZERO

from models import Account, get_account_type_labels, translate_account_name, TreasuryAccount, Reservation, Supplier, Collection, SupplierPayment, Employee, Expense
from . import templates, get_db
from services.accounting_service import AccountingService
import auth


def setup_accounting_routes(app):
    @app.get("/accounting/chart", response_class=HTMLResponse)
    def chart_of_accounts_page(request: Request, db: Session = Depends(get_db),
                               user=Depends(auth.require_permission("accounting.manage"))):
        accounts = db.query(Account).order_by(Account.account_type, Account.id).all()
        roots = [a for a in accounts if not a.parent_id]
        asc = AccountingService(db)
        balances = {a.id: asc.compute_account_balance(a) for a in accounts}
        type_totals = {}
        for a in roots:
            type_totals[a.account_type] = balances.get(a.id, 0)
        lang = request.session.get("lang", "en")
        return templates.TemplateResponse(request, "chart_of_accounts.html", {
            "request": request, "page_title": "الشجرة المحاسبية (Chart of Accounts)", "active": "accounting",
            "roots": roots, "all_accounts": accounts,
            "ACCOUNT_TYPE_LABELS": get_account_type_labels(lang),
            "translate_account_name": lambda n: translate_account_name(n, lang),
            "balances": balances, "type_totals": type_totals,
        })

    @app.post("/accounting/chart/{account_id}/opening-balance")
    def update_opening_balance(account_id: int, opening_balance: float = Form(0), db: Session = Depends(get_db),
                               user=Depends(auth.require_permission("accounting.manage"))):
        a = db.query(Account).get(account_id)
        if a:
            a.opening_balance = D(opening_balance)
            db.commit()
        return RedirectResponse("/accounting/chart", status_code=303)

    @app.post("/accounting/chart/add")
    def add_account(name: str = Form(...), account_type: str = Form(...), code: str = Form(""),
                    parent_id: int = Form(None), db: Session = Depends(get_db),
                    user=Depends(auth.require_permission("accounting.manage"))):
        db.add(Account(name=name, account_type=account_type, code=code, parent_id=parent_id or None, is_system=0))
        db.commit()
        return RedirectResponse("/accounting/chart", status_code=303)

    @app.post("/accounting/chart/{account_id}/delete")
    def delete_account(account_id: int, db: Session = Depends(get_db),
                       user=Depends(auth.require_permission("accounting.manage"))):
        a = db.query(Account).get(account_id)
        if a and not a.is_system:
            db.delete(a)
            db.commit()
        return RedirectResponse("/accounting/chart", status_code=303)

    @app.get("/accounting/balance-sheet", response_class=HTMLResponse)
    def balance_sheet_page(request: Request, db: Session = Depends(get_db),
                           user=Depends(auth.require_permission("accounting.manage"))):
        asc = AccountingService(db)
        roots = [a for a in db.query(Account).filter(Account.parent_id == None).all()]
        balances = {a.id: asc.compute_account_balance(a) for a in roots}
        total_assets = balances.get(next((a.id for a in roots if a.account_type == "asset"), None), DECIMAL_ZERO)
        total_liabilities = balances.get(next((a.id for a in roots if a.account_type == "liability"), None), DECIMAL_ZERO)
        total_equity = balances.get(next((a.id for a in roots if a.account_type == "equity"), None), DECIMAL_ZERO)
        treasury_acc = db.query(Account).filter(Account.key == "treasury").first()
        ar_acc = db.query(Account).filter(Account.key == "ar").first()
        ap_acc = db.query(Account).filter(Account.key == "ap").first()
        treasury_total = asc.compute_account_balance(treasury_acc) if treasury_acc else DECIMAL_ZERO
        accounts_receivable = asc.compute_account_balance(ar_acc) if ar_acc else DECIMAL_ZERO
        accounts_payable = asc.compute_account_balance(ap_acc) if ap_acc else DECIMAL_ZERO
        equity = total_assets - total_liabilities if total_assets and total_liabilities else total_equity
        return templates.TemplateResponse(request, "balance_sheet.html", {
            "request": request, "page_title": "الميزانية (Balance Sheet)", "active": "accounting",
            "treasury_total": treasury_total, "accounts_receivable": accounts_receivable,
            "total_assets": total_assets, "accounts_payable": accounts_payable,
            "total_liabilities": total_liabilities, "equity": equity,
        })

    @app.get("/accounting/reconcile", response_class=HTMLResponse)
    def reconcile_page(request: Request, db: Session = Depends(get_db),
                       user=Depends(auth.require_permission("accounting.manage"))):
        svc = AccountingService(db)
        discrepancies = svc.verify_all()
        return templates.TemplateResponse(request, "reconcile.html", {
            "request": request, "page_title": "مطابقة الأرصدة (Reconcile)", "active": "reconcile",
            "discrepancies": discrepancies,
            "synced": request.query_params.get("synced"),
        })

    @app.post("/accounting/reconcile/sync")
    def reconcile_sync(request: Request, db: Session = Depends(get_db),
                       user=Depends(auth.require_permission("accounting.manage"))):
        svc = AccountingService(db)
        svc.sync_all_caches()
        db.commit()
        return RedirectResponse("/accounting/reconcile?synced=1", status_code=303)
