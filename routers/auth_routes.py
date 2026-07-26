from fastapi import Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy.orm import Session
import json, datetime, time, uuid, os

from models import SessionLocal, User, verify_password, hash_password, needs_rehash
from . import templates, get_db, get_lang
from i18n import get_text_map
import auth

SESSION_COOKIE = "session_token"


def _get_ip(request: Request) -> str:
    return request.headers.get("CF-Connecting-IP") or \
           request.headers.get("X-Forwarded-For", "").split(",")[0].strip() or \
           (request.client.host if request.client else "unknown")


def _complete_login(request: Request, db: Session, user: User, ip: str, ua: str):
    """يُستدعى بعد نجاح كل التحققات (باسورد + MFA لو مفعّل) — بينشئ الجلسة فعليًا."""
    auth.reset_failure(db, user)
    token = auth.create_session(db, user, request)
    auth.record_login_attempt(db, user.username, ip, ua, success=True, user_id=user.id)
    request.session["user_id"] = user.id
    request.session.pop("pending_mfa_user_id", None)
    response = RedirectResponse("/", status_code=303)
    response.set_cookie(SESSION_COOKIE, token, httponly=True, samesite="lax", max_age=auth.IDLE_TIMEOUT_SECONDS)
    lang_pref = request.cookies.get("lang_pref", "en")
    request.session["lang"] = lang_pref
    return response


def setup_auth_routes(app):
    @app.get("/login", response_class=HTMLResponse)
    def login_page(request: Request, error: str = None):
        return templates.TemplateResponse(request, "login.html", {"request": request, "error": error})

    @app.post("/login")
    def login_submit(request: Request, username: str = Form(...), password: str = Form(...),
                     mfa_code: str = Form(""), db: Session = Depends(get_db)):
        ip = _get_ip(request)
        ua = request.headers.get("user-agent")

        # 1) القفل التدريجي لكل اسم مستخدم (لو موجود)
        user = db.query(User).filter(User.username == username).first()
        if user and auth.is_locked(user):
            secs = auth.lock_remaining_seconds(user)
            auth.record_login_attempt(db, username, ip, ua, success=False, reason="locked", user_id=user.id)
            return RedirectResponse(f"/login?error=الحساب+مقفل+مؤقتاً.+حاول+بعد+{secs}+ثانية", status_code=303)

        # 2) التحقق من كلمة المرور
        if not user or not user.is_active or not verify_password(password, user.password_hash):
            if user:
                auth.register_failure(db, user)
                reason = "wrong_password"
            else:
                reason = "no_such_user"
            auth.record_login_attempt(db, username, ip, ua, success=False, reason=reason,
                                      user_id=(user.id if user else None))
            # عدّاد فاشل لكل IP أيضاً (يمنع تخمين أسماء كثيرة من نفس المصدر)
            ip_fails = auth.recent_ip_failures(db, ip)
            msg = "بيانات+الدخول+غير+صحيحة"
            if user and auth.is_locked(user):
                msg = f"الحساب+مقفل+مؤقتاً.+حاول+بعد+{auth.lock_remaining_seconds(user)}+ثانية"
            elif ip_fails >= auth.MAX_FAILED:
                msg = "محاولات+كثيرة+من+هذا+المصدر.+انتظر+قليلاً"
            return RedirectResponse(f"/login?error={msg}", status_code=303)

        # 3) التحقق من MFA — لو المستخدم مفعّلها، منكملش تسجيل الدخول مباشرة،
        #    منروّح لصفحة إدخال الرمز على حدة (خطوة تانية منفصلة)
        if getattr(user, "mfa_enabled", 0):
            if needs_rehash(user.password_hash):
                user.password_hash = hash_password(password)
                db.commit()
            request.session["pending_mfa_user_id"] = user.id
            return RedirectResponse("/login/mfa", status_code=303)

        # 4) نجاح من غير MFA: نصفر المحاولات الفاشلة وننشئ جلسة
        if needs_rehash(user.password_hash):
            user.password_hash = hash_password(password)
            db.commit()
        return _complete_login(request, db, user, ip, ua)

    @app.get("/login/mfa", response_class=HTMLResponse)
    def login_mfa_page(request: Request, error: str = None):
        if not request.session.get("pending_mfa_user_id"):
            return RedirectResponse("/login", status_code=303)
        return templates.TemplateResponse(request, "login_mfa.html", {"request": request, "error": error})

    @app.post("/login/mfa")
    def login_mfa_submit(request: Request, mfa_code: str = Form(...), db: Session = Depends(get_db)):
        ip = _get_ip(request)
        ua = request.headers.get("user-agent")
        uid = request.session.get("pending_mfa_user_id")
        if not uid:
            return RedirectResponse("/login", status_code=303)
        user = db.query(User).get(uid)
        if not user or not user.is_active:
            request.session.pop("pending_mfa_user_id", None)
            return RedirectResponse("/login", status_code=303)
        if user and auth.is_locked(user):
            secs = auth.lock_remaining_seconds(user)
            request.session.pop("pending_mfa_user_id", None)
            return RedirectResponse(f"/login?error=الحساب+مقفل+مؤقتاً.+حاول+بعد+{secs}+ثانية", status_code=303)
        if not auth.verify_mfa_code(user.mfa_secret or "", mfa_code):
            auth.register_failure(db, user)
            auth.record_login_attempt(db, user.username, ip, ua, success=False, reason="mfa_failed", user_id=user.id)
            return RedirectResponse("/login/mfa?error=رمز+التحقق+غير+صحيح", status_code=303)
        return _complete_login(request, db, user, ip, ua)

    @app.get("/logout")
    @app.post("/logout")
    def logout(request: Request, db: Session = Depends(get_db)):
        token = request.cookies.get(SESSION_COOKIE)
        if token:
            auth.logout_session(db, token)
        response = RedirectResponse("/login", status_code=303)
        response.delete_cookie(SESSION_COOKIE)
        request.session.clear()
        return response

    @app.get("/set-language/{lang}")
    def set_language(lang: str, request: Request):
        if lang not in ("ar", "en"):
            lang = "en"
        request.session["lang"] = lang
        referer = request.headers.get("referer", "/")
        response = RedirectResponse(referer, status_code=303)
        response.set_cookie("lang_pref", lang, max_age=60*60*24*365, httponly=False, samesite="lax")
        return response

    @app.get("/debug-lang")
    def debug_lang(request: Request):
        lang = request.session.get("lang", "en")
        text_map = get_text_map(lang)
        return {
            "lang": lang,
            "translations_count": len(text_map),
            "sample": {
                "لوحة التحكم الرئيسية": text_map.get("لوحة التحكم الرئيسية"),
                "الحجوزات": text_map.get("الحجوزات"),
                "الفنادق": text_map.get("الفنادق"),
            }
        }

    # ─── الجلسات النشطة + تسجيل الخروج من كل الأجهزة ───
    @app.get("/sessions", response_class=HTMLResponse)
    def sessions_page(request: Request, db: Session = Depends(get_db)):
        user = auth.require_login(request, db)
        token = request.cookies.get(SESSION_COOKIE)
        sessions = auth.active_sessions(db, user.id)
        now = datetime.datetime.utcnow()
        return templates.TemplateResponse(request, "sessions.html", {
            "request": request,
            "sessions": sessions, "current_token": token, "now": now,
        })

    @app.post("/sessions/logout-all")
    def logout_all(request: Request, db: Session = Depends(get_db)):
        user = auth.require_login(request, db)
        token = request.cookies.get(SESSION_COOKIE)
        auth.logout_all_sessions(db, user.id, except_token=None)
        response = RedirectResponse("/login", status_code=303)
        response.delete_cookie(SESSION_COOKIE)
        request.session.clear()
        return response

    @app.post("/sessions/{token}/logout")
    def logout_one(token: str, request: Request, db: Session = Depends(get_db)):
        user = auth.require_login(request, db)
        auth.logout_session(db, token)
        return RedirectResponse("/sessions", status_code=303)

    # ─── تغيير كلمة المرور ───
    @app.get("/change-password", response_class=HTMLResponse)
    def change_password_page(request: Request, error: str = None, success: str = None):
        return templates.TemplateResponse(request, "change_password.html",
                                          {"request": request, "error": error, "success": success})

    @app.post("/change-password")
    def change_password_submit(request: Request, current: str = Form(...), new1: str = Form(...),
                               new2: str = Form(...), db: Session = Depends(get_db)):
        user = auth.require_login(request, db)
        if not verify_password(current, user.password_hash):
            return RedirectResponse("/change-password?error=كلمة+المرور+الحالية+غير+صحيحة", status_code=303)
        if new1 != new2:
            return RedirectResponse("/change-password?error=كلمتا+المرور+غير+متطابقتين", status_code=303)
        if len(new1) < 8:
            return RedirectResponse("/change-password?error=كلمة+المرور+يجب+ألا+تقل+عن+8+أحرف", status_code=303)
        user.password_hash = hash_password(new1)
        user.password_changed_at = datetime.datetime.utcnow()
        db.commit()
        return RedirectResponse("/change-password?success=تم+تغيير+كلمة+المرور+بنجاح", status_code=303)

    # ─── المصادقة الثنائية (MFA) — إعداد ذاتي لأي مستخدم ───
    @app.get("/settings/mfa", response_class=HTMLResponse)
    def mfa_settings_page(request: Request, db: Session = Depends(get_db)):
        user = auth.require_login(request, db)
        mfa_enabled = bool(user.mfa_enabled)
        provisioning_uri = ""
        secret_display = ""
        if not mfa_enabled:
            if not user.mfa_secret:
                user.mfa_secret = auth.generate_mfa_secret()
                db.commit()
            provisioning_uri = auth.mfa_provisioning_uri(user.mfa_secret, user.username)
            secret_display = user.mfa_secret
        return templates.TemplateResponse(request, "mfa_settings.html", {
            "request": request, "page_title": "المصادقة الثنائية - Two-Factor Auth", "active": "mfa",
            "mfa_enabled": mfa_enabled, "provisioning_uri": provisioning_uri, "secret_display": secret_display,
        })

    @app.post("/settings/mfa/enable")
    async def mfa_enable(request: Request, mfa_code: str = Form(...), db: Session = Depends(get_db)):
        user = auth.require_login(request, db)
        if not auth.verify_mfa_code(user.mfa_secret or "", mfa_code):
            return RedirectResponse("/settings/mfa?error=رمز+التحقق+غير+صحيح،+حاول+تاني", status_code=303)
        user.mfa_enabled = 1
        db.commit()
        return RedirectResponse("/settings/mfa", status_code=303)

    @app.post("/settings/mfa/disable")
    def mfa_disable(request: Request, password: str = Form(...), db: Session = Depends(get_db)):
        user = auth.require_login(request, db)
        if not verify_password(password, user.password_hash):
            return RedirectResponse("/settings/mfa?error=كلمة+المرور+غير+صحيحة", status_code=303)
        user.mfa_enabled = 0
        user.mfa_secret = None
        db.commit()
        return RedirectResponse("/settings/mfa", status_code=303)

    # ─── استعادة كلمة المرور (توكن آمن) ───
    # مفيش SMTP مضبوط -> نولّد توكن ونعرضه للمدير/المالك (أو نعتمد على سؤال/توكن)
    @app.get("/forgot-password", response_class=HTMLResponse)
    def forgot_page(request: Request, error: str = None, token: str = None):
        return templates.TemplateResponse(request, "forgot_password.html",
                                          {"request": request, "error": error, "token": token})

    @app.post("/forgot-password")
    def forgot_submit(request: Request, username: str = Form(...), db: Session = Depends(get_db)):
        user = db.query(User).filter(User.username == username).first()
        if not user:
            return RedirectResponse("/forgot-password?error=لا+يوجد+مستخدم+بهذا+الاسم", status_code=303)
        # فقط المدير/المالك يقدر يولّد توكن (لمنع إساءة الاستخدام) — أو نولّده لأي مستخدم
        token = auth.create_reset_token(db, user, ip=_get_ip(request))
        return RedirectResponse(f"/forgot-password?token={token}", status_code=303)

    @app.get("/reset-password", response_class=HTMLResponse)
    def reset_page(request: Request, token: str = "", error: str = None):
        return templates.TemplateResponse(request, "reset_password.html",
                                          {"request": request, "token": token, "error": error})

    @app.post("/reset-password")
    def reset_submit(request: Request, token: str = Form(...), new1: str = Form(...), new2: str = Form(...),
                     db: Session = Depends(get_db)):
        if new1 != new2:
            return RedirectResponse(f"/reset-password?token={token}&error=كلمتا+المرور+غير+متطابقتين", status_code=303)
        if len(new1) < 8:
            return RedirectResponse(f"/reset-password?token={token}&error=كلمة+المرور+ضعيفة", status_code=303)
        user = auth.verify_reset_token(db, token)
        if not user:
            return RedirectResponse("/reset-password?error=توكن+غير+صالح+أو+منتهٍ", status_code=303)
        user.password_hash = hash_password(new1)
        user.password_changed_at = datetime.datetime.utcnow()
        user.failed_login_count = 0
        user.locked_until = None
        db.commit()
        auth.consume_reset_token(db, token)
        return RedirectResponse("/login?success=تم+تعيين+كلمة+المرور+سجّل+الدخول", status_code=303)

    @app.get("/i18n-auto.js")
    def i18n_auto_js(request: Request):
        lang = request.session.get("lang", "en")
        text_map = get_text_map(lang) if lang == "en" else {}
        return Response(
            content=_make_i18n_js(lang, text_map),
            media_type="application/javascript; charset=utf-8",
            headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"}
        )


def _make_i18n_js(lang, text_map):
    import json
    return f"""
(function () {{
  window.APP_LANG = {json.dumps(lang)};
  window.AUTO_TRANSLATE = {json.dumps(text_map, ensure_ascii=False)};
  if (window.APP_LANG !== "en") return;
  const dictionary = window.AUTO_TRANSLATE || {{}};
  function normalizeText(text) {{ return String(text || "").replace(/\\s+/g, " ").trim(); }}
  function hasArabic(text) {{ return /[\\u0600-\\u06FF]/.test(String(text || "")); }}
  function translateString(value) {{
    let result = String(value || "");
    const keys = Object.keys(dictionary).sort(function(a, b) {{ return b.length - a.length; }});
    keys.forEach(function(key) {{ if (key && dictionary[key] && result.includes(key)) result = result.split(key).join(dictionary[key]); }});
    return result;
  }}
  function translateTextNodes(root) {{
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {{
      acceptNode: function(node) {{
        const parent = node.parentElement;
        if (!parent) return NodeFilter.FILTER_REJECT;
        const tag = parent.tagName.toLowerCase();
        if (["script","style","textarea","code","pre"].includes(tag)) return NodeFilter.FILTER_REJECT;
        const text = normalizeText(node.nodeValue);
        if (!text || !hasArabic(text)) return NodeFilter.FILTER_REJECT;
        return NodeFilter.FILTER_ACCEPT;
      }}
    }});
    const nodes = [];
    while (walker.nextNode()) nodes.push(walker.currentNode);
    nodes.forEach(function(node) {{ const nv = translateString(node.nodeValue); if (nv !== node.nodeValue) node.nodeValue = nv; }});
  }}
  function translateAttributes(root) {{
    const elements = root.querySelectorAll("[placeholder],[title],[aria-label],input[type='submit'],input[type='button'],input[type='reset']");
    elements.forEach(function(el) {{
      ["placeholder","title","aria-label"].forEach(function(attr) {{ const v = el.getAttribute(attr); if (v && hasArabic(v)) el.setAttribute(attr, translateString(v)); }});
      if (el.tagName === "INPUT") {{ const t = (el.getAttribute("type")||"").toLowerCase(); if (["button","submit","reset"].includes(t) && hasArabic(el.value)) el.value = translateString(el.value); }}
    }});
  }}
  function applyTranslation(root) {{ if (root) {{ translateTextNodes(root); translateAttributes(root); }} }}
  function boot() {{
    document.documentElement.lang = "en"; document.documentElement.dir = "ltr"; document.body.dir = "ltr"; document.body.classList.add("lang-en");
    applyTranslation(document.body);
    const observer = new MutationObserver(function(mutations) {{ mutations.forEach(function(m) {{ m.addedNodes.forEach(function(n) {{ if (n.nodeType === 1) applyTranslation(n); }}); }}); }});
    observer.observe(document.body, {{ childList: true, subtree: true }});
  }}
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot); else boot();
}})();
"""
