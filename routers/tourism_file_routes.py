import datetime
from fastapi import Request, Form, Depends, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from models import TourismFile
from . import templates, get_db
import auth
from services.storage_service import storage_service, StorageError, StorageSecurityError


def setup_tourism_file_routes(app):
    @app.get("/tourism-files", response_class=HTMLResponse)
    def tourism_files_page(request: Request, db: Session = Depends(get_db),
                           user=Depends(auth.require_permission("files.view"))):
        files = db.query(TourismFile).order_by(TourismFile.id.desc()).all()
        return templates.TemplateResponse(request, "tourism_files.html", {
            "request": request, "page_title": "ملفات السياحة", "active": "files", "files": files,
        })

    @app.post("/tourism-files/add")
    def add_tourism_file(title: str = Form(...), category: str = Form(""), related_to: str = Form(""),
                         notes: str = Form(""), file: UploadFile = File(None), request: Request = None,
                         db: Session = Depends(get_db),
                         user=Depends(auth.require_permission("files.manage"))):
        file_path = None
        if file and file.filename:
            try:
                sf = storage_service.save(file, owner_user_id=getattr(user, "id", None),
                                          category="doc", record_type="tourism_file",
                                          db=db, request=request)
                file_path = f"/secure-files/{sf.id}"
            except (StorageError, StorageSecurityError) as e:
                return RedirectResponse(f"/tourism-files?error={_q(str(e))}", status_code=303)
        db.add(TourismFile(created_date=datetime.date.today(), title=title, category=category,
                           related_to=related_to, file_path=file_path, notes=notes))
        db.commit()
        return RedirectResponse("/tourism-files", status_code=303)

    @app.post("/tourism-files/{file_id}/delete")
    def delete_tourism_file(file_id: int, request: Request, db: Session = Depends(get_db),
                            user=Depends(auth.require_permission("files.manage"))):
        f = db.query(TourismFile).get(file_id)
        if f:
            if f.file_path and f.file_path.startswith("/secure-files/"):
                try:
                    sf_id = int(f.file_path.rsplit("/", 1)[-1])
                    sf = db.query(__import__("models").SecureFile).get(sf_id)
                    if sf:
                        storage_service.delete(sf, db=db, request=request)
                        db.delete(sf)
                except Exception:
                    pass
            db.delete(f)
            db.commit()
        return RedirectResponse("/tourism-files", status_code=303)


def _q(s: str) -> str:
    from urllib.parse import quote
    return quote(s)
