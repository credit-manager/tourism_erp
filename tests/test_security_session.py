"""
اختبارات الأمان الجديدة:
- Rate Limiting بقاعدة بيانات + قفل تدريجي (لكل IP و username).
- تسجيل محاولات الدخول (ناجحة/فاشلة) في login_attempts.
- جلسات نشطة: إنشاء/خمول/تسجيل خروج من الكل.
- تغيير كلمة المرور + استعادة آمنة بتوكن.
"""
import re
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main
import models
import auth
from fastapi.testclient import TestClient


def _csrf(client, url):
    return re.search(r'name="csrf_token" value="([^"]+)"', client.get(url).text).group(1)


def _reset_user(db, username):
    u = db.query(models.User).filter(models.User.username == username).first()
    u.failed_login_count = 0
    u.locked_until = None
    u.mfa_enabled = 0  # تعطيل MFA للاختبار
    db.commit()
    return u


def test_progressive_lockout_and_audit():
    db = models.SessionLocal()
    try:
        _reset_user(db, "owner")
        c = TestClient(main.app)
        for _ in range(auth.MAX_FAILED):
            c.post("/login", data={"username": "owner", "password": "WRONG"}, follow_redirects=False)
        u = db.query(models.User).filter(models.User.username == "owner").first()
        assert u.locked_until is not None, "user should be locked"
        fails = db.query(models.LoginAttempt).filter(
            models.LoginAttempt.username == "owner", models.LoginAttempt.success == 0).count()
        assert fails >= auth.MAX_FAILED
    finally:
        db.close()


def test_successful_login_creates_session_and_audit():
    db = models.SessionLocal()
    try:
        _reset_user(db, "owner")
        c = TestClient(main.app)
        r = c.post("/login", data={"username": "owner", "password": "Owner@123"}, follow_redirects=False)
        assert r.headers.get("location") == "/"
        assert c.cookies.get("session_token")
        ok = db.query(models.LoginAttempt).filter(
            models.LoginAttempt.username == "owner", models.LoginAttempt.success == 1).count()
        assert ok >= 1
        u = db.query(models.User).filter(models.User.username == "owner").first()
        sess = db.query(models.UserSession).filter(
            models.UserSession.user_id == u.id, models.UserSession.is_active == 1).count()
        assert sess >= 1
    finally:
        db.close()


def test_change_password_flow():
    db = models.SessionLocal()
    try:
        _reset_user(db, "owner")
        c = TestClient(main.app)
        c.post("/login", data={"username": "owner", "password": "Owner@123"}, follow_redirects=False)
        csrf = _csrf(c, "/change-password")
        r = c.post("/change-password", data={
            "current": "Owner@123", "new1": "NewPass123", "new2": "NewPass123", "csrf_token": csrf},
            follow_redirects=False)
        assert "success" in (r.headers.get("location") or "")
        # تسجيل دخول بكلمة جديدة
        _reset_user(db, "owner")
        r = c.post("/login", data={"username": "owner", "password": "NewPass123"}, follow_redirects=False)
        assert r.headers.get("location") == "/"
        # إرجاع الكلمة الأصلية للأمان
        u = db.query(models.User).filter(models.User.username == "owner").first()
        u.password_hash = models.hash_password("Owner@123")
        db.commit()
    finally:
        db.close()


def test_secure_reset_token():
    db = models.SessionLocal()
    try:
        u = db.query(models.User).filter(models.User.username == "owner").first()
        token = auth.create_reset_token(db, u, ip="test")
        assert auth.verify_reset_token(db, token).id == u.id
        c = TestClient(main.app)
        csrf = _csrf(c, "/reset-password?token=" + token)
        r = c.post("/reset-password", data={
            "token": token, "new1": "TempPass123", "new2": "TempPass123", "csrf_token": csrf},
            follow_redirects=False)
        assert r.headers.get("location", "").startswith("/login")
        db.rollback()  # نقرأ من DB نظيف (تجنب snapshot المعاملة النشطة)
        assert auth.verify_reset_token(db, token) is None  # استُهلك
        u.password_hash = models.hash_password("Owner@123")
        db.commit()
    finally:
        db.close()


def test_logout_all_sessions():
    db = models.SessionLocal()
    try:
        u = db.query(models.User).filter(models.User.username == "owner").first()
        auth.logout_all_sessions(db, u.id)
        n = db.query(models.UserSession).filter(
            models.UserSession.user_id == u.id, models.UserSession.is_active == 1).count()
        assert n == 0
    finally:
        db.close()


def test_idle_timeout_inactive():
    from datetime import timedelta
    db = models.SessionLocal()
    try:
        u = db.query(models.User).filter(models.User.username == "owner").first()
        db.query(models.UserSession).filter(models.UserSession.token == "idle_chk").delete()
        db.add(models.UserSession(
            token="idle_chk", user_id=u.id,
            last_seen=auth._now() - timedelta(seconds=auth.IDLE_TIMEOUT_SECONDS + 60), is_active=1))
        db.commit()
        assert auth.get_active_session(db, "idle_chk") is None
        db.query(models.UserSession).filter(models.UserSession.token == "idle_chk").delete()
        db.commit()
    finally:
        db.close()
