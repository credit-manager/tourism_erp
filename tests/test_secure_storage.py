"""
اختبارات التخزين الآمن:
- رفع ملف سليم (txt/pdf/jpeg) وتخزينه في storage/secure خارج static.
- رفض الملفات التنفيذية (exe/magic MZ).
- رفض الملفات بامتداد مزيّف لا يطابق المحتوى.
- رفض الملفات الأكبر من الحد.
- منع Path Traversal.
- مسار تنزيل محمي: مجهول يُرجع صفحة الدخول (وليس الملف)، ومصرّح له يحصل على الملف + تسجيل Audit.
"""
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main
import models
from fastapi.testclient import TestClient

from services.storage_service import storage_service, StorageSecurityError, StorageError


class _Up:
    def __init__(self, name, data):
        self.filename = name
        self.file = io.BytesIO(data)


def _clean():
    db = models.SessionLocal()
    try:
        for sf in db.query(models.SecureFile).all():
            try:
                os.remove(storage_service.read_path(sf.stored_name))
            except Exception:
                pass
            db.delete(sf)
        db.query(models.AuditLog).filter(models.AuditLog.table_name == "secure_files").delete()
        db.commit()
    finally:
        db.close()


def test_valid_text_upload():
    _clean()
    db = models.SessionLocal()
    try:
        sf = storage_service.save(_Up("note.txt", b"hello world"), owner_user_id=1, category="doc", db=db)
        assert sf.mime == "text/plain"
        assert os.path.exists(storage_service.read_path(sf.stored_name))
    finally:
        db.close()
        _clean()


def test_executable_rejected_by_magic():
    db = models.SessionLocal()
    try:
        try:
            storage_service.save(_Up("evil.exe", b"MZ" + b"\x00" * 20), db=db)
            assert False, "exe should be blocked"
        except StorageSecurityError:
            pass
    finally:
        db.close()


def test_fake_extension_rejected():
    db = models.SessionLocal()
    try:
        try:
            storage_service.save(_Up("fake.pdf", b"just text not pdf"), db=db)
            assert False, "fake pdf should be blocked"
        except StorageSecurityError:
            pass
    finally:
        db.close()


def test_oversize_rejected():
    db = models.SessionLocal()
    try:
        try:
            storage_service.save(_Up("big.txt", b"x" * (11 * 1024 * 1024)), db=db)
            assert False, "oversize should be blocked"
        except StorageError:
            pass
    finally:
        db.close()


def test_traversal_blocked_in_safe_join():
    # read_path يطبّق basename أولاً (آمن)، لكن _safe_join يجب أن يرفض المسار الخارج
    try:
        storage_service._safe_join("../secret.txt")
        assert False, "traversal should be blocked"
    except StorageSecurityError:
        pass
    # اسم عادي آمن
    assert storage_service._safe_join("abc123.txt").endswith("abc123.txt")


def test_production_requires_av_when_missing(monkeypatch):
    # في الإنتاج ومن غير clamav مثبّت، يجب رفض الرفع (fail-closed)
    monkeypatch.setattr("services.storage_service.shutil_which", lambda name: None)
    prod = type(storage_service)(environment="production")
    db = models.SessionLocal()
    try:
        try:
            prod.save(_Up("doc.txt", b"hello"), db=db)
            assert False, "production without AV should reject"
        except StorageSecurityError:
            pass
    finally:
        # نظّف أي ملف يتيم تركه الفحص قبل الرفض
        for f in os.listdir(storage_service.storage_dir):
            if f.endswith(".txt"):
                try: os.remove(os.path.join(storage_service.storage_dir, f))
                except Exception: pass
        db.close()


def test_dev_allows_missing_av():
    # في التطوير بدون clamav، يجب السماح بالرفع
    import services.storage_service as ss
    orig = ss.shutil_which
    ss.shutil_which = lambda name: None
    db = models.SessionLocal()
    try:
        sf = storage_service.save(_Up("dev.txt", b"dev content"), db=db)
        db.commit()
        assert sf.id
    finally:
        db.close()
        ss.shutil_which = orig
        _clean()



def test_protected_download_requires_auth():
    _clean()
    client = TestClient(main.app)
    client.post("/login", data={"username": "owner", "password": "Owner@123"}, follow_redirects=False)
    db = models.SessionLocal()
    try:
        sf = storage_service.save(_Up("doc.txt", b"secret-content"), owner_user_id=1, category="doc", db=db)
        db.commit()
        sf_id = sf.id
    finally:
        db.close()

    anon = TestClient(main.app)
    r = anon.get(f"/secure-files/{sf_id}")
    # مجهول: لا يحصل على الملف (صفحة دخول HTML أو 401/403/404)
    assert r.headers.get("content-type", "").startswith("text/html") or r.status_code in (401, 403, 404)
    assert r.content != b"secret-content"

    r = client.get(f"/secure-files/{sf_id}")
    assert r.status_code == 200
    assert r.content == b"secret-content"
    assert r.headers.get("content-type", "").startswith("text/plain")

    db = models.SessionLocal()
    try:
        cnt = db.query(models.AuditLog).filter(
            models.AuditLog.action == "download", models.AuditLog.record_id == sf_id).count()
        assert cnt >= 1, f"download audit not logged (count={cnt})"
    finally:
        db.close()
    _clean()
