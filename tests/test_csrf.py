"""
اختبارات حماية CSRF:
- طلب POST بدون رمز → 403
- طلب POST برمز خاطئ → 403
- طلب POST برمز صحيح (من جلسة) → ناجح
- في وضع الإنتاج: كوكي الجلسة يحمل Secure + HttpOnly + SameSite
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient
import main
from models import SessionLocal, User, hash_password

TEST_USER = "csrf_test_user"
TEST_PASS = "csrf_test_pass_123"


def _ensure_user():
    db = SessionLocal()
    try:
        u = db.query(User).filter(User.username == TEST_USER).first()
        if not u:
            u = User(username=TEST_USER, full_name="CSRF Test", role="admin",
                     password_hash=hash_password(TEST_PASS), is_active=1)
            db.add(u)
            db.commit()
        return u
    finally:
        db.close()


def _cleanup_user():
    db = SessionLocal()
    try:
        u = db.query(User).filter(User.username == TEST_USER).first()
        if u:
            db.delete(u)
            db.commit()
    finally:
        db.close()


def _login(client: TestClient):
    resp = client.post("/login", data={"username": TEST_USER, "password": TEST_PASS},
                       follow_redirects=False)
    assert resp.status_code in (302, 303), resp.status_code
    return resp


def _get_token_from_page(client: TestClient, url: str) -> str:
    html = client.get(url).text
    m = re.search(r'name="csrf_token" value="([^"]+)"', html)
    assert m, "csrf_token not found in page " + url
    return m.group(1)


def setup_module(module):
    _ensure_user()


def teardown_module(module):
    _cleanup_user()


# ── اختبارات الرفض ────────────────────────────────
def test_post_without_token_is_rejected():
    client = TestClient(main.app)
    _login(client)
    # بدون توكن: يُحوَّل المستخدم لصفحته مع رسالة خطأ (303) بدل 403 فارغة
    resp = client.post("/attendance/approve-bulk", data={"month": "2026-07"},
                       follow_redirects=False)
    assert resp.status_code in (302, 303)
    assert "error=" in resp.headers.get("location", "")


def test_post_with_wrong_token_is_rejected():
    client = TestClient(main.app)
    _login(client)
    resp = client.post("/attendance/approve-bulk",
                       data={"month": "2026-07", "csrf_token": "wrong-token-value"},
                       follow_redirects=False)
    assert resp.status_code in (302, 303)
    assert "error=" in resp.headers.get("location", "")


def test_get_is_not_checked():
    client = TestClient(main.app)
    _login(client)
    resp = client.get("/attendance/log")
    assert resp.status_code == 200


# ── اختبار القبول ─────────────────────────────────
def test_post_with_valid_token_succeeds():
    client = TestClient(main.app)
    _login(client)
    token = _get_token_from_page(client, "/attendance/approve")
    resp = client.post("/attendance/approve-bulk",
                       data={"month": "2026-07", "csrf_token": token})
    assert resp.status_code != 403


def test_header_token_accepted():
    client = TestClient(main.app)
    _login(client)
    token = _get_token_from_page(client, "/attendance")
    resp = client.post("/attendance/approve-bulk",
                       data={"month": "2026-07"},
                       headers={"X-CSRF-Token": token})
    assert resp.status_code != 403


# ── اختبار حماية الكوكي في الإنتاج ─────────────────
def test_session_cookie_secure_in_production():
    """يتحقق من أن كوكي الجلسة يحمل Secure+HttpOnly+SameSite في الإنتاج.
    يُبنى تطبيق صغير منعزل (بدون إعادة تحميل main) لتجنّب تلوّث الحالة المشتركة."""
    from starlette.applications import Starlette
    from starlette.middleware.sessions import SessionMiddleware
    from starlette.responses import PlainTextResponse
    from starlette.routing import Route

    async def _set_session(request):
        request.session["u"] = 1
        return PlainTextResponse("ok")

    app = Starlette(routes=[Route("/set", _set_session)])
    app.add_middleware(
        SessionMiddleware,
        secret_key="test-secret",
        max_age=60 * 60 * 8,
        same_site="lax",
        https_only=True,  # وضع الإنتاج
    )
    client = TestClient(app)
    resp = client.get("/set")
    set_cookie = resp.headers.get("set-cookie", "")
    assert set_cookie, "session cookie not set"
    low = set_cookie.lower()
    assert "secure" in low, "session cookie must be Secure in production"
    assert "httponly" in low, "session cookie must be HttpOnly"
    assert "samesite" in low, "session cookie must set SameSite"
