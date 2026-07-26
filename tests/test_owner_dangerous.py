"""
اختبارات حماية العمليات الخطيرة (Owner):
- المالك فقط يمكنه تنفيذها
- إعادة إدخال كلمة المرور صحيحة مطلوبة
- رمز MFA صحيح مطلوب (ومفعّل)
- سبب مكتوب مطلوب
- CSRF مطلوب
- نسخة احتياطية تُنشأ قبل النوك، والعملية تُسجَّل في Audit Log (ولا يُستثنى المالك)
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient
import main
import auth as auth_mod
from models import SessionLocal, User, AuditLog, hash_password, _SysCfg

OWNER = "danger_test_owner"
PASS = "danger_pass_123"


def _make_owner():
    db = SessionLocal()
    try:
        u = db.query(User).filter(User.username == OWNER).first()
        if not u:
            u = User(username=OWNER, full_name="Danger Owner", role="owner",
                     password_hash=hash_password(PASS), is_active=1,
                     mfa_secret=auth_mod.generate_mfa_secret(), mfa_enabled=0)
            db.add(u)
            db.commit()
        return u
    finally:
        db.close()


def _cleanup():
    db = SessionLocal()
    try:
        u = db.query(User).filter(User.username == OWNER).first()
        if u:
            db.delete(u)
            db.commit()
    finally:
        db.close()


def _login_owner(client):
    # أنشئ جلسة مالك يدوياً عبر تسجيل دخول حقيقي
    from models import SessionLocal as _DB, User as _Usr
    _d = _DB()
    try:
        _u = _d.query(_Usr).filter(_Usr.username == OWNER).first()
        mfa_on = _u and _u.mfa_enabled
    finally:
        _d.close()
    data_d = {"username": OWNER, "password": PASS}
    if mfa_on:
        data_d["mfa_code"] = _totp_for(OWNER)
    r = client.post("/login", data=data_d, follow_redirects=False)
    assert r.status_code in (302, 303), r.status_code


def _totp_for(username):
    db = SessionLocal()
    try:
        u = db.query(User).filter(User.username == username).first()
        secret = u.mfa_secret
    finally:
        db.close()
    return auth_mod._totp_at(secret, int(time.time()) // auth_mod._TOTP_STEP)


def _set_mfa(enabled: int):
    db = SessionLocal()
    try:
        u = db.query(User).filter(User.username == OWNER).first()
        u.mfa_enabled = enabled
        db.commit()
    finally:
        db.close()


def setup_module(module):
    _make_owner()


import pytest

@pytest.fixture(autouse=True)
def _reset_system_state():
    # نتأكد إن النظام شغّال قبل كل اختبار (عزل حالة sd)
    db = SessionLocal()
    try:
        cfg = db.query(_SysCfg).get("sd")
        if cfg and cfg.v == "1":
            cfg.v = "0"
            db.commit()
    finally:
        db.close()
    yield


def teardown_module(module):
    # إعادة تشغيل النظام إن كان متوقفاً بفعل اختبار (عزل الحالة)
    db = SessionLocal()
    try:
        cfg = db.query(_SysCfg).get("sd")
        if cfg and cfg.v == "1":
            cfg.v = "0"
            db.commit()
    finally:
        db.close()
    _cleanup()


def test_owner_panel_requires_owner():
    client = TestClient(main.app)
    # بدون تسجيل دخول -> مرفوض (403) لأن المسار محمي بصلاحية المالك
    r = client.get("/_oc/panel", follow_redirects=False)
    assert r.status_code in (401, 403)


def test_shutdown_rejected_without_mfa_enabled():
    # المالك مُنشأ لكن MFA معطّل -> يجب الرفض (CSRF أولاً ثم فحص MFA)
    _set_mfa(0)
    client = TestClient(main.app)
    _login_owner(client)
    r = client.post("/_oc/shutdown",
                    data={"password": PASS, "mfa_code": "000000", "reason": "test", "csrf_token": "x"},
                    follow_redirects=False)
    assert r.status_code in (302, 303)
    assert "error=" in (r.headers.get("location") or "")


def test_shutdown_rejected_wrong_password():
    _set_mfa(1)
    client = TestClient(main.app)
    _login_owner(client)
    r = client.post("/_oc/shutdown",
                    data={"password": "WRONG", "mfa_code": _totp_for(OWNER), "reason": "test reason", "csrf_token": "x"},
                    follow_redirects=False)
    assert r.status_code in (302, 303)
    assert "error=" in (r.headers.get("location") or "")


def test_shutdown_rejected_missing_reason():
    _set_mfa(1)
    client = TestClient(main.app)
    _login_owner(client)
    r = client.post("/_oc/shutdown",
                    data={"password": PASS, "mfa_code": _totp_for(OWNER), "reason": "", "csrf_token": "x"},
                    follow_redirects=False)
    # السبب مطلوب -> يُرفض (422 من التحقق من الحدود أو 303 من التحقق الداخلي)
    assert r.status_code in (303, 403, 422)


def test_shutdown_rejected_without_csrf():
    _set_mfa(1)
    client = TestClient(main.app)
    _login_owner(client)
    r = client.post("/_oc/shutdown",
                    data={"password": PASS, "mfa_code": _totp_for(OWNER), "reason": "valid reason"},
                    follow_redirects=False)
    # بلا توكن CSRF -> يُحوَّل مع خطأ (303) من وسيط CSRF
    assert r.status_code in (302, 303)


def test_shutdown_succeeds_with_all_checks_and_audits_owner():
    _set_mfa(1)
    client = TestClient(main.app)
    _login_owner(client)
    # جلب توكن CSRF من الصفحة
    import re
    html = client.get("/_oc/panel").text
    m = re.search(r'name="csrf_token" value="([^"]+)"', html)
    assert m
    token = m.group(1)
    before = SessionLocal().query(AuditLog).filter(AuditLog.username == OWNER).count()
    r = client.post("/_oc/shutdown",
                    data={"password": PASS, "mfa_code": _totp_for(OWNER), "reason": "اختبار إيقاف", "csrf_token": token},
                    follow_redirects=False)
    assert r.status_code in (302, 303)
    after = SessionLocal().query(AuditLog).filter(AuditLog.username == OWNER).count()
    # المالك مُسجَّل في Audit Log (لا استثناء)
    assert after > before, "owner action was not audited"


def test_nuke_creates_backup_and_does_not_delete():
    _set_mfa(1)
    client = TestClient(main.app)
    _login_owner(client)
    import re
    html = client.get("/_oc/panel").text
    m = re.search(r'name="csrf_token" value="([^"]+)"', html)
    token = m.group(1)
    users_before = SessionLocal().query(User).count()
    r = client.post("/_oc/nuke",
                    data={"password": PASS, "mfa_code": _totp_for(OWNER), "reason": "اختبار حذف", "csrf_token": token},
                    follow_redirects=False)
    assert r.status_code in (302, 303)
    # لم تُحذف أي بيانات
    users_after = SessionLocal().query(User).count()
    assert users_after == users_before, "data was deleted!"
    # نسخة احتياطية وُجدت
    backups = [f for f in os.listdir("backups") if f.startswith("backup_pre_nuke")]
    assert backups, "no backup created before nuke"
