import datetime
from fastapi import Request, Form, Depends, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from currency_utils import D, DECIMAL_ZERO

from models import TreasuryAccount, TreasuryTransaction, TreasuryTransfer, Expense, Currency, JournalEntry, CashClosing
from . import templates, get_db, translate_account_name, save_upload
import auth


def setup_treasury_routes(app):
    @app.get("/treasury", response_class=HTMLResponse)
    def treasury_page(request: Request, db: Session = Depends(get_db),
                      user=Depends(auth.require_permission("treasury.view"))):
        accounts = db.query(TreasuryAccount).all()
        transactions = db.query(TreasuryTransaction).order_by(TreasuryTransaction.id.desc()).limit(30).all()
        lang = request.session.get("lang", "en")
        return templates.TemplateResponse(request, "treasury.html", {
            "request": request, "accounts": accounts, "transactions": transactions,
            "page_title": "الخزنة", "active": "treasury", "lang": lang,
            "translate_account_name": lambda n: translate_account_name(n, lang),
        })

    @app.post("/treasury/transaction")
    def add_transaction(account_id: int = Form(...), type: str = Form(...), amount: float = Form(...),
                        description: str = Form(""), db: Session = Depends(get_db),
                        user=Depends(auth.require_permission("treasury.manage"))):
        d_amount = D(amount)
        if d_amount > DECIMAL_ZERO:
            from services.treasury_service import TreasuryService
            try:
                TreasuryService(db).create_transaction(account_id, type, d_amount, description, user=user)
            except Exception as e:
                db.rollback()
                return RedirectResponse(f"/treasury?error={e}", status_code=303)
        db.commit()
        return RedirectResponse("/treasury", status_code=303)

    # â”€â”€â”€ Expenses â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    @app.get("/expenses", response_class=HTMLResponse)
    def expenses_page(request: Request, db: Session = Depends(get_db),
                      user=Depends(auth.require_permission("treasury.view"))):
        expenses = db.query(Expense).order_by(Expense.id.desc()).all()
        accounts = db.query(TreasuryAccount).all()
        currencies = db.query(Currency).all()
        return templates.TemplateResponse(request, "expenses.html", {
            "request": request, "expenses": expenses, "page_title": "المصروفات", "active": "expenses",
            "accounts": accounts, "currencies": currencies,
        })

    @app.post("/expenses/add")
    def add_expense(category: str = Form(...), amount: float = Form(...), account_id: int = Form(None),
                    description: str = Form(""), currency_id: int = Form(None),
                    exchange_rate: float = Form(1), db: Session = Depends(get_db),
                    user=Depends(auth.require_permission("expenses.manage"))):
        d_amount = D(amount)
        d_rate = D(exchange_rate)
        amount_currency = d_amount
        amount_base = d_amount * d_rate if d_rate > 0 else d_amount
        from services.treasury_service import TreasuryService, AccountNotSelectedError
        ts = TreasuryService(db)
        try:
            account = ts.resolve_account(account_id, "expense")
        except AccountNotSelectedError as e:
            return RedirectResponse(f"/expenses?error={e}", status_code=303)
        expense = Expense(category=category, amount=d_amount, description=description, date=datetime.date.today(),
                          account_id=account.id, currency_id=currency_id,
                          amount_currency=amount_currency, amount_base=amount_base,
                          exchange_rate=d_rate, status="draft", created_by=user.username)
        db.add(expense)
        db.commit()
        return RedirectResponse("/expenses", status_code=303)

    # ??? Workflow transitions (Treasury) ???
    @app.post("/treasury/{txn_id}/submit")
    def submit_treasury_txn(txn_id: int, db: Session = Depends(get_db),
                            user=Depends(auth.require_permission("treasury.manage"))):
        t = db.query(TreasuryTransaction).get(txn_id)
        if not t: return RedirectResponse("/treasury", status_code=303)
        from services.workflow_service import WorkflowService
        WorkflowService(db).submit(t, user)
        db.commit()
        return RedirectResponse("/treasury", status_code=303)

    @app.post("/treasury/{txn_id}/approve")
    def approve_treasury_txn(txn_id: int, db: Session = Depends(get_db),
                             user=Depends(auth.require_permission("treasury.manage"))):
        t = db.query(TreasuryTransaction).get(txn_id)
        if not t: return RedirectResponse("/treasury", status_code=303)
        from services.workflow_service import WorkflowService, WorkflowError
        try:
            WorkflowService(db).review(t, user, approved=True)
            db.commit()
        except WorkflowError:
            db.rollback()
        return RedirectResponse("/treasury", status_code=303)

    @app.post("/treasury/{txn_id}/post")
    def post_treasury_txn(txn_id: int, db: Session = Depends(get_db),
                          user=Depends(auth.require_permission("treasury.manage"))):
        t = db.query(TreasuryTransaction).get(txn_id)
        if not t: return RedirectResponse("/treasury", status_code=303)
        from services.treasury_service import TreasuryService, InsufficientBalanceError, AccountNotSelectedError
        ts_svc = TreasuryService(db)
        if t.type == "out":
            try:
                account = ts_svc.resolve_account(t.account_id, "withdrawal")
                ts_svc.validate_withdrawal(account.id, D(t.amount), t.description or "سحب من الخزنة")
                if not t.account_id:
                    t.account_id = account.id
            except (InsufficientBalanceError, AccountNotSelectedError) as e:
                db.rollback()
                return RedirectResponse(f"/treasury?error={e}", status_code=303)
        from services.workflow_service import WorkflowService
        WorkflowService(db).post(t, user)
        db.commit()
        return RedirectResponse("/treasury", status_code=303)

    @app.post("/treasury/{txn_id}/cancel")
    def cancel_treasury_txn(txn_id: int, db: Session = Depends(get_db),
                            user=Depends(auth.require_permission("treasury.manage"))):
        t = db.query(TreasuryTransaction).get(txn_id)
        if not t: return RedirectResponse("/treasury", status_code=303)
        from services.workflow_service import WorkflowService
        WorkflowService(db).cancel(t, user)
        from services.treasury_service import TreasuryService
        ts = TreasuryService(db)
        if t.type == "out":
            ts.restore_balance(t.account_id, D(t.amount))
        elif t.type == "in":
            ts.deduct_balance(t.account_id, D(t.amount))
        db.commit()
        return RedirectResponse("/treasury", status_code=303)

    # ??? Workflow transitions (Expenses) ???
    @app.post("/expenses/{expense_id}/submit")
    def submit_expense(expense_id: int, db: Session = Depends(get_db),
                       user=Depends(auth.require_permission("expenses.manage"))):
        e = db.query(Expense).get(expense_id)
        if not e: return RedirectResponse("/expenses", status_code=303)
        from services.workflow_service import WorkflowService
        WorkflowService(db).submit(e, user)
        db.commit()
        return RedirectResponse("/expenses", status_code=303)

    @app.post("/expenses/{expense_id}/approve")
    def approve_expense(expense_id: int, db: Session = Depends(get_db),
                        user=Depends(auth.require_permission("expenses.manage"))):
        e = db.query(Expense).get(expense_id)
        if not e: return RedirectResponse("/expenses", status_code=303)
        from services.workflow_service import WorkflowService, WorkflowError
        try:
            WorkflowService(db).review(e, user, approved=True)
            db.commit()
        except WorkflowError:
            db.rollback()
            return RedirectResponse("/expenses?error=workflow_error", status_code=303)
        return RedirectResponse("/expenses", status_code=303)

    @app.post("/expenses/{expense_id}/post")
    def post_expense(expense_id: int, db: Session = Depends(get_db),
                     user=Depends(auth.require_permission("expenses.manage"))):
        from services.treasury_service import TreasuryService
        try:
            TreasuryService(db).post_expense(expense_id, user=user)
            db.commit()
        except Exception as e:
            db.rollback()
            return RedirectResponse(f"/expenses?error={e}", status_code=303)
        return RedirectResponse("/expenses", status_code=303)

    @app.post("/expenses/{expense_id}/cancel")
    def cancel_expense(expense_id: int, db: Session = Depends(get_db),
                       user=Depends(auth.require_permission("expenses.manage"))):
        e = db.query(Expense).get(expense_id)
        if not e: return RedirectResponse("/expenses", status_code=303)
        from services.workflow_service import WorkflowService
        WorkflowService(db).cancel(e, user)
        db.commit()
        return RedirectResponse("/expenses", status_code=303)

    # ─── Treasury Transfers ─────────────────────────────────
    @app.get("/transfers", response_class=HTMLResponse)
    def transfers_page(request: Request, db: Session = Depends(get_db),
                       user=Depends(auth.require_permission("treasury.view"))):
        transfers = db.query(TreasuryTransfer).order_by(TreasuryTransfer.id.desc()).all()
        accounts = db.query(TreasuryAccount).all()
        currencies = db.query(Currency).all()
        return templates.TemplateResponse(request, "transfers.html", {
            "request": request, "transfers": transfers, "accounts": accounts,
            "currencies": currencies,
            "page_title": "تحويلات الخزنة", "active": "transfers",
        })

    @app.get("/transfers/{transfer_id}", response_class=HTMLResponse)
    def transfer_detail(transfer_id: int, request: Request, db: Session = Depends(get_db),
                        user=Depends(auth.require_permission("treasury.view"))):
        t = db.query(TreasuryTransfer).get(transfer_id)
        if not t:
            return RedirectResponse("/transfers", status_code=303)
        txns = db.query(TreasuryTransaction).filter(
            TreasuryTransaction.description.like(f"%{t.description or ''}%"),
            TreasuryTransaction.date == t.date,
        ).order_by(TreasuryTransaction.id).all()
        return templates.TemplateResponse(request, "transfer_detail.html", {
            "request": request, "transfer": t, "txns": txns,
            "page_title": f"تحويل #{t.id}", "active": "transfers",
        })

    @app.post("/transfers/add")
    def add_transfer(from_account_id: int = Form(...), to_account_id: int = Form(...),
                     amount: float = Form(...), fee: float = Form(0),
                     exchange_rate: float = Form(1.0), description: str = Form(""),
                     db: Session = Depends(get_db),
                     user=Depends(auth.require_permission("treasury.manage"))):
        from services.treasury_service import TreasuryService
        try:
            TreasuryService(db).create_transfer(
                from_account_id, to_account_id, amount, D(fee),
                D(exchange_rate), description, user=user)
            db.commit()
        except Exception as e:
            db.rollback()
            return RedirectResponse(f"/transfers?error={e}", status_code=303)
        return RedirectResponse("/transfers", status_code=303)

    @app.post("/transfers/{transfer_id}/submit")
    def submit_transfer(transfer_id: int, db: Session = Depends(get_db),
                        user=Depends(auth.require_permission("treasury.manage"))):
        t = db.query(TreasuryTransfer).get(transfer_id)
        if not t: return RedirectResponse("/transfers", status_code=303)
        from services.workflow_service import WorkflowService
        WorkflowService(db).submit(t, user)
        db.commit()
        return RedirectResponse(f"/transfers/{transfer_id}", status_code=303)

    @app.post("/transfers/{transfer_id}/approve")
    def approve_transfer(transfer_id: int, db: Session = Depends(get_db),
                         user=Depends(auth.require_permission("treasury.manage"))):
        t = db.query(TreasuryTransfer).get(transfer_id)
        if not t: return RedirectResponse("/transfers", status_code=303)
        from services.workflow_service import WorkflowService, WorkflowError
        try:
            WorkflowService(db).review(t, user, approved=True)
            db.commit()
        except WorkflowError:
            db.rollback()
        return RedirectResponse(f"/transfers/{transfer_id}", status_code=303)

    @app.post("/transfers/{transfer_id}/reject")
    def reject_transfer(transfer_id: int, db: Session = Depends(get_db),
                        user=Depends(auth.require_permission("treasury.manage"))):
        t = db.query(TreasuryTransfer).get(transfer_id)
        if not t: return RedirectResponse("/transfers", status_code=303)
        from services.workflow_service import WorkflowService, WorkflowError
        try:
            WorkflowService(db).review(t, user, approved=False)
            db.commit()
        except WorkflowError:
            db.rollback()
        return RedirectResponse(f"/transfers/{transfer_id}", status_code=303)

    @app.post("/transfers/{transfer_id}/post")
    def post_transfer(transfer_id: int, db: Session = Depends(get_db),
                      user=Depends(auth.require_permission("treasury.manage"))):
        from services.treasury_service import TreasuryService
        try:
            TreasuryService(db).post_transfer(transfer_id, user=user)
            db.commit()
        except Exception as e:
            db.rollback()
            return RedirectResponse(f"/transfers?error={e}", status_code=303)
        return RedirectResponse(f"/transfers/{transfer_id}", status_code=303)

    @app.post("/transfers/{transfer_id}/cancel")
    def cancel_transfer(transfer_id: int, db: Session = Depends(get_db),
                        user=Depends(auth.require_permission("treasury.manage"))):
        from services.treasury_service import TreasuryService
        try:
            TreasuryService(db).cancel_transfer(transfer_id, user=user)
            db.commit()
        except Exception as e:
            db.rollback()
            return RedirectResponse(f"/transfers?error={e}", status_code=303)
        return RedirectResponse("/transfers", status_code=303)

    # ─── Cash Closing ────────────────────────────────────
    @app.get("/treasury/closing", response_class=HTMLResponse)
    def closing_page(request: Request, db: Session = Depends(get_db),
                     user=Depends(auth.require_permission("treasury.view"))):
        closings = db.query(CashClosing).order_by(CashClosing.id.desc()).all()
        accounts = db.query(TreasuryAccount).all()
        return templates.TemplateResponse(request, "closing.html", {
            "request": request, "closings": closings, "accounts": accounts,
            "page_title": "الجرد اليومي", "active": "closing",
        })

    @app.post("/treasury/closing/add")
    async def add_closing(request: Request, account_id: int = Form(...),
                          closing_date: str = Form(...),
                          actual_balance: float = Form(...),
                          reason: str = Form(""),
                          attachment: UploadFile = File(None),
                          db: Session = Depends(get_db),
                          user=Depends(auth.require_permission("treasury.manage"))):
        from services.treasury_service import TreasuryService
        ts = TreasuryService(db)
        last_d = ts.get_balance(account_id)
        actual_d = D(str(actual_balance))
        diff_d = actual_d - last_d
        if diff_d != DECIMAL_ZERO and not reason.strip():
            return RedirectResponse("/treasury/closing?error=يجب+إدخال+سبب+الفرق+عند+وجود+عجز+أو+زيادة", status_code=303)
        closing = CashClosing(
            account_id=account_id,
            closing_date=datetime.date.fromisoformat(closing_date),
            system_balance=last_d,
            actual_balance=actual_d,
            difference=diff_d,
            reason=reason,
            status="draft", created_by=user.username,
        )
        if attachment and attachment.filename:
            closing.attachment_path = save_upload(attachment)
        db.add(closing)
        db.flush()
        if diff_d == DECIMAL_ZERO:
            from services.workflow_service import WorkflowService
            ws = WorkflowService(db)
            ws.submit(closing, user)
            ws.review(closing, user, approved=True)
            ws.post(closing, user)
            closing.status = "posted"
        db.commit()
        return RedirectResponse("/treasury/closing", status_code=303)

    @app.post("/treasury/closing/{closing_id}/submit")
    def submit_closing(closing_id: int, db: Session = Depends(get_db),
                       user=Depends(auth.require_permission("treasury.manage"))):
        c = db.query(CashClosing).get(closing_id)
        if not c: return RedirectResponse("/treasury/closing", status_code=303)
        from services.workflow_service import WorkflowService
        WorkflowService(db).submit(c, user)
        db.commit()
        return RedirectResponse("/treasury/closing", status_code=303)

    @app.post("/treasury/closing/{closing_id}/approve")
    def approve_closing(closing_id: int, db: Session = Depends(get_db),
                        user=Depends(auth.require_permission("treasury.manage"))):
        c = db.query(CashClosing).get(closing_id)
        if not c: return RedirectResponse("/treasury/closing", status_code=303)
        from services.workflow_service import WorkflowService
        WorkflowService(db).review(c, user, approved=True)
        db.commit()
        return RedirectResponse("/treasury/closing", status_code=303)

    @app.post("/treasury/closing/{closing_id}/post")
    def post_closing(closing_id: int, db: Session = Depends(get_db),
                     user=Depends(auth.require_permission("treasury.manage"))):
        from services.treasury_service import TreasuryService
        try:
            TreasuryService(db).post_closing(closing_id, user=user)
            db.commit()
        except Exception as e:
            db.rollback()
            return RedirectResponse(f"/treasury/closing?error={e}", status_code=303)
        return RedirectResponse("/treasury/closing", status_code=303)

    @app.post("/treasury/closing/{closing_id}/cancel")
    def cancel_closing(closing_id: int, db: Session = Depends(get_db),
                       user=Depends(auth.require_permission("treasury.manage"))):
        from services.treasury_service import TreasuryService
        try:
            TreasuryService(db).cancel_closing(closing_id, user=user)
            db.commit()
        except Exception as e:
            db.rollback()
            return RedirectResponse(f"/treasury/closing?error={e}", status_code=303)
        return RedirectResponse("/treasury/closing", status_code=303)

    @app.get("/treasury/closing/report", response_class=HTMLResponse)
    def closing_report(request: Request, date: str = None, account_id: int = None,
                       db: Session = Depends(get_db),
                       user=Depends(auth.require_permission("treasury.view"))):
        q = db.query(CashClosing)
        if date:
            q = q.filter(CashClosing.closing_date == datetime.date.fromisoformat(date))
        if account_id:
            q = q.filter(CashClosing.account_id == account_id)
        q = q.order_by(CashClosing.closing_date.desc(), CashClosing.id.desc())
        closings = q.all()
        accounts = db.query(TreasuryAccount).all()
        return templates.TemplateResponse(request, "closing_report.html", {
            "request": request, "closings": closings, "accounts": accounts,
            "page_title": "تقرير الجرد اليومي", "active": "closing",
        })

    @app.get("/treasury/closing/{closing_id}", response_class=HTMLResponse)
    def closing_detail(closing_id: int, request: Request, db: Session = Depends(get_db),
                       user=Depends(auth.require_permission("treasury.view"))):
        c = db.query(CashClosing).get(closing_id)
        if not c:
            return RedirectResponse("/treasury/closing", status_code=303)
        accounts = db.query(TreasuryAccount).all()
        return templates.TemplateResponse(request, "closing.html", {
            "request": request, "closings": [c], "accounts": accounts,
            "page_title": f"جرد #{c.id}", "active": "closing",
        })

