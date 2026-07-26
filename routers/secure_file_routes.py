"""
مسارات الملفات الآمنة:
- تنزيل محمي /secure-files/{id}: يتحقق من تسجيل الدخول + الصلاحية + ارتباط الملف بالسجل.
- حذف محمي /secure-files/{id}/delete: للمالك أو صاحب الصلاحية.
"""
import os
import urllib.parse
from fastapi import Request, Depends
from fastapi.responses import Response, RedirectResponse
from sqlalchemy.orm import Session

from models import SecureFile
from . import get_db
import auth
from services.storage_service import storage_service, StorageSecurityError


def _can_access(user, sf) -> bool:
    """يتحقق أن المستخدم مصرّح له الوصول للملف (صلاحية files.view أو صاحب الرفع أو صاحب السجل)."""
    if user is None:
        return False
    if auth.has_permission(user, "files.view"):
        return True
    if sf.owner_user_id and sf.owner_user_id == getattr(user, "id", None):
        return True
    if sf.record_type == "contract" and auth.has_permission(user, "contracts.view"):
        return True
    if sf.record_type == "reservation" and auth.has_permission(user, "reservations.view"):
        return True
    return False


def setup_secure_file_routes(app):
    @app.get("/secure-files/{file_id}")
    def download_secure_file(file_id: int, request: Request, db: Session = Depends(get_db),
                             user=Depends(auth.require_permission("files.view"))):
        sf = db.query(SecureFile).get(file_id)
        if not sf:
            return Response("Not Found", status_code=404)
        if not _can_access(user, sf):
            return Response("Forbidden", status_code=403)
        try:
            path = storage_service.read_path(sf.stored_name)
        except StorageSecurityError:
            return Response("Forbidden", status_code=403)
        if not os.path.exists(path):
            return Response("Not Found", status_code=404)
        try:
            with open(path, "rb") as f:
                data = f.read()
        except Exception:
            return Response("Not Found", status_code=404)
        storage_service.log_download(sf, db=db, request=request)
        db.commit()
        headers = {
            "Content-Disposition": f"attachment; filename={urllib.parse.quote(sf.original_name)}",
            "Content-Type": sf.mime or "application/octet-stream",
            "X-Content-Type-Options": "nosniff",
        }
        return Response(content=data, headers=headers)

    @app.post("/secure-files/{file_id}/delete")
    def delete_secure_file(file_id: int, request: Request, db: Session = Depends(get_db),
                           user=Depends(auth.require_permission("files.manage"))):
        sf = db.query(SecureFile).get(file_id)
        if not sf:
            return RedirectResponse("/tourism-files", status_code=303)
        storage_service.delete(sf, db=db, request=request)
        db.delete(sf)
        db.commit()
        back = request.query_params.get("back") or "/tourism-files"
        return RedirectResponse(back, status_code=303)
