import datetime
from fastapi import Request, Form, Depends, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from currency_utils import D, DECIMAL_ZERO

from models import Contract, Supplier, Hotel, generate_contract_number, SecureFile
from . import templates, get_db
import auth
from services.storage_service import storage_service, StorageError, StorageSecurityError
from urllib.parse import quote as _quote


def _save_secure(file, user, db, request, record_type, record_id=None, category="contract"):
    """يرفع الملف عبر StorageService ويرجع رابط التنزيل الآمن، أو None عند عدم وجود ملف/خطأ."""
    if not (file and file.filename):
        return None
    sf = storage_service.save(file, owner_user_id=getattr(user, "id", None),
                              category=category, record_type=record_type,
                              record_id=record_id, db=db, request=request)
    return f"/secure-files/{sf.id}"


def setup_contract_routes(app):
    @app.get("/contracts", response_class=HTMLResponse)
    def contracts_page(request: Request, db: Session = Depends(get_db),
                       user=Depends(auth.require_permission("contracts.view"))):
        contracts = db.query(Contract).order_by(Contract.id.desc()).all()
        suppliers = db.query(Supplier).all()
        hotels = db.query(Hotel).all()
        today = datetime.date.today()
        expiring_soon = [c for c in contracts if c.end_date and 0 <= (c.end_date - today).days <= 30 and not c.is_expired]
        expired = [c for c in contracts if c.is_expired and c.status != "cancelled"]
        return templates.TemplateResponse(request, "contracts.html", {
            "request": request, "page_title": "العقود (Contracts)", "active": "contracts",
            "contracts": contracts, "suppliers": suppliers, "hotels": hotels,
            "expiring_soon": expiring_soon, "expired": expired,
        })

    @app.post("/contracts/add")
    def add_contract(title: str = Form(...), party_type: str = Form("supplier"),
                     supplier_id: int = Form(None), hotel_id: int = Form(None),
                     start_date: str = Form(None), end_date: str = Form(None),
                     contract_value: float = Form(0), notes: str = Form(""),
                     file: UploadFile = File(None), db: Session = Depends(get_db),
                     user=Depends(auth.require_permission("contracts.manage"))):
        def parse_date(s):
            try: return datetime.datetime.strptime(s, "%Y-%m-%d").date()
            except Exception: return None
        contract = Contract(contract_number=generate_contract_number(db), created_date=datetime.date.today(),
                            title=title, party_type=party_type,
                            supplier_id=supplier_id if party_type == "supplier" else None,
                            hotel_id=hotel_id if party_type == "hotel" else None,
                            start_date=parse_date(start_date), end_date=parse_date(end_date),
                            contract_value=D(contract_value), status="active",
                            notes=notes)
        db.add(contract)
        db.flush()
        if file and file.filename:
            try:
                contract.file_path = _save_secure(file, user, db, request, "contract", record_id=contract.id)
            except (StorageError, StorageSecurityError) as e:
                return RedirectResponse(f"/contracts?error={_quote(str(e))}", status_code=303)
        db.commit()
        return RedirectResponse("/contracts", status_code=303)

    @app.post("/contracts/{contract_id}/edit")
    def edit_contract(contract_id: int, title: str = Form(...), party_type: str = Form("supplier"),
                      supplier_id: int = Form(None), hotel_id: int = Form(None),
                      start_date: str = Form(None), end_date: str = Form(None),
                      contract_value: float = Form(0), status: str = Form("active"),
                      notes: str = Form(""), file: UploadFile = File(None), db: Session = Depends(get_db),
                      user=Depends(auth.require_permission("contracts.manage"))):
        def parse_date(s):
            try: return datetime.datetime.strptime(s, "%Y-%m-%d").date()
            except Exception: return None
        c = db.query(Contract).get(contract_id)
        if c:
            c.title, c.party_type = title, party_type
            c.supplier_id = supplier_id if party_type == "supplier" else None
            c.hotel_id = hotel_id if party_type == "hotel" else None
            c.start_date, c.end_date = parse_date(start_date), parse_date(end_date)
            c.contract_value, c.status, c.notes = D(contract_value), status, notes
            if file and file.filename:
                # حذف الملف القديم إن وُجد
                if c.file_path and c.file_path.startswith("/secure-files/"):
                    try:
                        old = db.query(SecureFile).get(int(c.file_path.rsplit("/", 1)[-1]))
                        if old:
                            storage_service.delete(old, db=db, request=request)
                            db.delete(old)
                    except Exception:
                        pass
                try:
                    c.file_path = _save_secure(file, user, db, request, "contract", record_id=c.id)
                except (StorageError, StorageSecurityError) as e:
                    return RedirectResponse(f"/contracts?error={_quote(str(e))}", status_code=303)
            db.commit()
        return RedirectResponse("/contracts", status_code=303)

    @app.post("/contracts/{contract_id}/delete")
    def delete_contract(contract_id: int, request: Request, db: Session = Depends(get_db),
                        user=Depends(auth.require_permission("contracts.manage"))):
        c = db.query(Contract).get(contract_id)
        if c:
            if c.file_path and c.file_path.startswith("/secure-files/"):
                try:
                    sf = db.query(SecureFile).get(int(c.file_path.rsplit("/", 1)[-1]))
                    if sf:
                        storage_service.delete(sf, db=db, request=request)
                        db.delete(sf)
                except Exception:
                    pass
            db.delete(c)
            db.commit()
        return RedirectResponse("/contracts", status_code=303)
