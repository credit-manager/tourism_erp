import os, datetime
from fastapi import Request, Depends, Form, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from models import BankStatement, BankTransaction, TreasuryTransaction, TreasuryAccount
from . import templates, get_db, save_upload
from services.bank_reconciliation_service import BankReconciliationService
import auth


ALLOWED_EXTS = {".csv", ".xls", ".xlsx"}


def setup_bank_reconciliation_routes(app):
    @app.get("/treasury/bank", response_class=HTMLResponse)
    def bank_list(request: Request, db: Session = Depends(get_db),
                  user=Depends(auth.require_permission("treasury.view"))):
        statements = db.query(BankStatement).order_by(BankStatement.id.desc()).all()
        accounts = db.query(TreasuryAccount).filter(TreasuryAccount.type == "bank").all()
        return templates.TemplateResponse(request, "bank_reconciliation.html", {
            "request": request, "statements": statements, "accounts": accounts,
            "page_title": "تسوية كشوفات البنك", "active": "bank",
        })

    @app.post("/treasury/bank/import")
    async def import_statement(account_id: int = Form(...),
                               period_start: str = Form(None),
                               period_end: str = Form(None),
                               file: UploadFile = File(...),
                               db: Session = Depends(get_db),
                               user=Depends(auth.require_permission("treasury.manage"))):
        if not file.filename:
            return RedirectResponse("/treasury/bank?error=الملف+مطلوب", status_code=303)
        ext = os.path.splitext(file.filename)[1].lower()
        if ext not in ALLOWED_EXTS:
            return RedirectResponse("/treasury/bank?error=صيغة+الملف+غير+مدعومة+CSV+أو+Excel", status_code=303)
        file_path = save_upload(file, ALLOWED_EXTS)
        svc = BankReconciliationService(db)
        try:
            svc.import_statement(account_id, f".{file_path}", period_start, period_end, user.username)
            db.commit()
        except Exception as e:
            db.rollback()
            return RedirectResponse(f"/treasury/bank?error={str(e)}", status_code=303)
        return RedirectResponse("/treasury/bank", status_code=303)

    @app.get("/treasury/bank/{statement_id}", response_class=HTMLResponse)
    def bank_statement_detail(statement_id: int, request: Request, db: Session = Depends(get_db),
                              user=Depends(auth.require_permission("treasury.view"))):
        stmt = db.query(BankStatement).get(statement_id)
        if not stmt:
            return RedirectResponse("/treasury/bank", status_code=303)
        svc = BankReconciliationService(db)
        matched = svc.get_matched(statement_id)
        unmatched = svc.get_unmatched(statement_id)
        summary = svc.get_statement_summary(statement_id)
        internal_txns = db.query(TreasuryTransaction).filter(
            TreasuryTransaction.account_id == stmt.account_id,
        ).order_by(TreasuryTransaction.date.desc()).limit(500).all()
        return templates.TemplateResponse(request, "bank_statement_detail.html", {
            "request": request, "statement": stmt, "matched": matched,
            "unmatched": unmatched, "summary": summary,
            "internal_txns": internal_txns,
            "page_title": f"كشف حساب #{statement_id}", "active": "bank",
        })

    @app.post("/treasury/bank/{statement_id}/match")
    def manual_match(statement_id: int, bank_txn_id: int = Form(...),
                     txn_id: int = Form(...), db: Session = Depends(get_db),
                     user=Depends(auth.require_permission("treasury.manage"))):
        try:
            BankReconciliationService(db).manual_match(bank_txn_id, txn_id)
            db.commit()
        except Exception:
            db.rollback()
        return RedirectResponse(f"/treasury/bank/{statement_id}", status_code=303)

    @app.post("/treasury/bank/{statement_id}/unmatch")
    def manual_unmatch(statement_id: int, bank_txn_id: int = Form(...),
                       db: Session = Depends(get_db),
                       user=Depends(auth.require_permission("treasury.manage"))):
        try:
            BankReconciliationService(db).manual_unmatch(bank_txn_id)
            db.commit()
        except Exception:
            db.rollback()
        return RedirectResponse(f"/treasury/bank/{statement_id}", status_code=303)

    @app.post("/treasury/bank/{statement_id}/mark-fee")
    def mark_bank_fee(statement_id: int, bank_txn_id: int = Form(...),
                      notes: str = Form(""), db: Session = Depends(get_db),
                      user=Depends(auth.require_permission("treasury.manage"))):
        try:
            BankReconciliationService(db).mark_bank_fee(bank_txn_id, notes)
            db.commit()
        except Exception:
            db.rollback()
        return RedirectResponse(f"/treasury/bank/{statement_id}", status_code=303)

    @app.post("/treasury/bank/{statement_id}/create-fee-entry")
    def create_fee_entry(statement_id: int, bank_txn_id: int = Form(...),
                         db: Session = Depends(get_db),
                         user=Depends(auth.require_permission("treasury.manage"))):
        try:
            BankReconciliationService(db).create_fee_entry(bank_txn_id, user.username)
            db.commit()
        except Exception:
            db.rollback()
        return RedirectResponse(f"/treasury/bank/{statement_id}", status_code=303)

    @app.post("/treasury/bank/{statement_id}/reconcile")
    def reconcile_statement(statement_id: int, db: Session = Depends(get_db),
                            user=Depends(auth.require_permission("treasury.manage"))):
        stmt = db.query(BankStatement).get(statement_id)
        if stmt:
            stmt.status = "reconciled"
            db.commit()
        return RedirectResponse(f"/treasury/bank/{statement_id}", status_code=303)
