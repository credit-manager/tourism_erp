"""
Tourism ERP — نظام إدارة سياحة متكامل
Version: Refactored (راوترات منفصلة)
"""
from fastapi import FastAPI, Request, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from sqlalchemy.orm import Session
import datetime, os, uuid

from models import SessionLocal, init_db, User, _SysCfg
import auth
from context import current_user_var
from i18n import I18N, get_text_map
from routers import templates, get_db, translate_description, get_lang, t
import jinja2

# ─── App Setup ─────────────────────────────────────────
app = FastAPI(title="Tourism ERP", dependencies=[Depends(auth.require_csrf)])

app.mount("/static", StaticFiles(directory="static"), name="static")
templates.env.globals["today"] = lambda: datetime.date.today().strftime("%Y-%m-%d")
templates.env.globals["has_permission"] = auth.has_permission
templates.env.globals["ROLE_LABELS"] = auth.ROLE_LABELS
templates.env.globals["PERMISSION_LABELS"] = auth.PERMISSION_LABELS
templates.env.globals["ALL_PERMISSIONS"] = auth.all_permission_keys()
templates.env.globals["t"] = t
templates.env.globals["get_text_map"] = get_text_map
templates.env.globals["LANG"] = get_lang
templates.env.globals["translate_desc"] = translate_description

@jinja2.pass_context
def _L(ctx, ar, en):
    req = ctx.get("request")
    lang = get_lang(req) if req else "en"
    return ar if lang == "ar" else en
templates.env.globals["L"] = _L
templates.env.filters["urlencode"] = lambda s: __import__("urllib.parse", fromlist=["quote"]).quote(str(s))

@jinja2.pass_context
def _csrf_token(ctx):
    req = ctx.get("request")
    return auth.get_csrf_token(req) if req else ""
templates.env.globals["csrf_token"] = _csrf_token
templates.env.globals["csrf_field"] = auth.csrf_field

from menu_config import get_menu_orientation, is_menu_visible
templates.env.globals["MENU_ORIENTATION"] = get_menu_orientation
templates.env.globals["is_menu_visible"] = is_menu_visible

# ─── Init DB ───────────────────────────────────────────
init_db()

PUBLIC_PATHS = {"/login", "/login/mfa", "/logout", "/set-language/ar", "/set-language/en",
                "/forgot-password", "/reset-password"}

# API v1 paths bypass session auth (using JWT/token in future)
API_PREFIXES = {"/api/v1/"}

# ─── Auth Middleware ────────────────────────────────────
class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if (path.startswith("/static") or path in PUBLIC_PATHS
            or path.startswith("/_oc/")
            or any(path.startswith(p) for p in API_PREFIXES)):
            return await call_next(request)
        user_id = request.session.get("user_id")
        current_user = None
        if user_id:
            db = SessionLocal()
            try:
                current_user = db.query(User).get(user_id)
                if current_user and not current_user.is_active:
                    current_user = None
            finally:
                db.close()
        if not current_user:
            return RedirectResponse("/login", status_code=303)
        if getattr(current_user, "role", "") != "owner":
            try:
                _db = SessionLocal()
                _cfg = _db.query(_SysCfg).get("sd")
                _db.close()
                if _cfg and _cfg.v == "1":
                    from starlette.responses import HTMLResponse
                    return HTMLResponse("""<!DOCTYPE html><html><head><meta charset="utf-8">
<title>النظام متوقف</title>
<style>body{font-family:sans-serif;display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0;background:#f8fafc;flex-direction:column;gap:16px;}
.box{background:#fff;border:1px solid #e5e7eb;border-radius:20px;padding:40px 60px;text-align:center;box-shadow:0 8px 24px rgba(0,0,0,.06);}
h2{color:#ef4444;margin:0 0 8px;}p{color:#6b7280;margin:0;}</style></head>
<body><div class="box"><h2>⛔ النظام متوقف مؤقتاً</h2>
<p>تم إيقاف النظام من قِبل الإدارة العليا.<br>يرجى المحاولة لاحقاً.</p></div></body></html>""", status_code=503)
            except: pass
        request.state.user = current_user
        token = current_user_var.set(current_user)
        try:
            response = await call_next(request)
        finally:
            current_user_var.reset(token)
        return response

app.add_middleware(AuthMiddleware)

# ─── Session Secret ────────────────────────────────────
def _get_session_secret() -> str:
    env_secret = os.environ.get("SESSION_SECRET_KEY")
    if env_secret:
        return env_secret
    secret_file = ".session_secret"
    if os.path.exists(secret_file):
        with open(secret_file, "r") as f:
            existing = f.read().strip()
            if existing:
                return existing
    new_secret = uuid.uuid4().hex + uuid.uuid4().hex
    try:
        with open(secret_file, "w") as f:
            f.write(new_secret)
    except: pass
    return new_secret

# ─── CSRF Protection (Dependency عام) ───────────────
# يُطبَّق عبر dependencies=[Depends(auth.require_csrf)] على كل الـ routes.
# هذا يتجنّب استهلاك جسم الطلب (مشكلة BaseHTTPMiddleware) ويشارك الجسم المخزّن
# مع معاملات Form الخاصة بالـ endpoint.

# ─── Security Headers Middleware ───────────────────
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """يضيف ترويسات حماية أساسية ضد clickjacking و MIME sniffing."""
    async def dispatch(self, request: Request, call_next):
        resp = await call_next(request)
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("Referrer-Policy", "same-origin")
        return resp

# ─── Session Cookie Hardening ──────────────────────
import os as _os
_IS_PROD = (_os.environ.get("ENV", _os.environ.get("ENVIRONMENT", "")).lower() in {"production", "prod", "staging"})

app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(
    SessionMiddleware,
    secret_key=_get_session_secret(),
    max_age=60 * 60 * 8,
    same_site="lax",
    https_only=_IS_PROD,
)

# ─── Exception Handlers ────────────────────────────────
@app.exception_handler(auth.NeedsLoginError)
def handle_needs_login(request: Request, exc):
    return RedirectResponse("/login", status_code=303)


from fastapi import HTTPException as _HTTPException

@app.exception_handler(_HTTPException)
def handle_http_exception(request: Request, exc: _HTTPException):
    # أخطاء CSRF (403) -> تحويل المستخدم لنفس الصفحة مع رسالة بدل صفحة فارغة
    if exc.status_code == 403 and exc.detail and "CSRF" in str(exc.detail):
        referer = request.headers.get("referer")
        base = referer if (referer and referer.startswith(str(request.base_url))) else "/"
        sep = "&" if "?" in base else "?"
        return RedirectResponse(base + sep + "error=" + "انتهت+صلة+الجلسة+أو+الرمز+غير+صالح.+أعد+المحاولة", status_code=303)
    from fastapi.responses import JSONResponse
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

@app.exception_handler(auth.PermissionDeniedError)
def handle_permission_denied(request: Request, exc):
    return templates.TemplateResponse(request, "403.html", {"request": request, "message": exc.message}, status_code=403)

@app.exception_handler(auth.DangerousActionDenied)
def handle_dangerous_denied(request: Request, exc):
    target = exc.redirect_to or "/_oc/panel"
    msg = exc.message.replace(" ", "+")
    return RedirectResponse(f"{target}?msg={msg}", status_code=303)

from routers import UnsupportedFileType, FileTooLarge
from urllib.parse import quote

@app.exception_handler(UnsupportedFileType)
def handle_unsupported_file_type(request: Request, exc):
    allowed = ", ".join(sorted({".jpg", ".jpeg", ".png", ".gif", ".webp", ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".txt"}))
    msg = quote(f"نوع الملف غير مدعوم ({exc.ext}). الأنواع المسموحة: {allowed}")
    referer = request.headers.get("referer", "/")
    sep = "&" if "?" in referer else "?"
    return RedirectResponse(f"{referer}{sep}error={msg}", status_code=303)

@app.exception_handler(FileTooLarge)
def handle_file_too_large(request: Request, exc):
    msg = quote(f"حجم الملف كبير جداً. الحد الأقصى المسموح 10MB")
    referer = request.headers.get("referer", "/")
    sep = "&" if "?" in referer else "?"
    return RedirectResponse(f"{referer}{sep}error={msg}", status_code=303)

# ─── Register All Routers ──────────────────────────────
from routers.auth_routes import setup_auth_routes
from routers.dashboard_routes import setup_dashboard_routes
from routers.customer_routes import setup_customer_routes
from routers.supplier_routes import setup_supplier_routes
from routers.employee_routes import setup_employee_routes
from routers.hotel_routes import setup_hotel_routes
from routers.service_routes import setup_service_routes
from routers.booking_routes import setup_booking_routes
from routers.reservation_routes import setup_reservation_routes
from routers.collection_routes import setup_collection_routes
from routers.contract_routes import setup_contract_routes
from routers.transport_routes import setup_transport_routes
from routers.ticket_routes import setup_ticket_routes
from routers.umrah_routes import setup_umrah_routes
from routers.tourism_file_routes import setup_tourism_file_routes
from routers.secure_file_routes import setup_secure_file_routes
from routers.police_routes import setup_police_routes
from routers.treasury_routes import setup_treasury_routes
from routers.report_routes import setup_report_routes
from routers.reconciliation_routes import setup_reconciliation_routes
from routers.setting_routes import setup_setting_routes
from routers.supplier_payment_routes import setup_supplier_payment_routes
from routers.accounting_routes import setup_accounting_routes
from routers.owner_routes import setup_owner_routes
from routers.sales_pipeline_routes import setup_sales_pipeline_routes
from routers.quotation_routes import setup_quotation_routes
from routers.statement_routes import setup_statement_routes
from routers.transition_routes import setup_transition_routes
from routers.workflow_routes import setup_workflow_routes
from routers.hotel_enhanced_routes import setup_hotel_enhanced_routes
from routers.supplier_confirmation_routes import setup_supplier_confirmation_routes
from routers.supplier_invoice_routes import setup_supplier_invoice_routes
from routers.bank_reconciliation_routes import setup_bank_reconciliation_routes
from routers.commission_policy_routes import setup_commission_policy_routes
from routers.payroll_run_routes import setup_payroll_run_routes
from routers.attendance_routes import setup_attendance_routes
from routers.notification_routes import setup_notification_routes
from routers.insights_routes import setup_insights_routes

# ضبط بيئة StorageService (يفعّل فحص Antivirus عند الإنتاج/الاستضافة)
from services.storage_service import storage_service as _storage_service
_storage_service.environment = "production" if _IS_PROD else "development"

setup_auth_routes(app)
setup_dashboard_routes(app)
setup_customer_routes(app)
setup_supplier_routes(app)
setup_employee_routes(app)
setup_hotel_routes(app)
setup_service_routes(app)
setup_booking_routes(app)
setup_reservation_routes(app)
setup_collection_routes(app)
setup_contract_routes(app)
setup_transport_routes(app)
setup_ticket_routes(app)
setup_umrah_routes(app)
setup_tourism_file_routes(app)
setup_secure_file_routes(app)
setup_police_routes(app)
setup_treasury_routes(app)
setup_report_routes(app)
setup_setting_routes(app)
setup_supplier_payment_routes(app)
setup_accounting_routes(app)
setup_owner_routes(app)
setup_reconciliation_routes(app)
setup_sales_pipeline_routes(app)
setup_quotation_routes(app)
setup_statement_routes(app)
setup_transition_routes(app)
setup_workflow_routes(app)
setup_hotel_enhanced_routes(app)
setup_supplier_confirmation_routes(app)
setup_supplier_invoice_routes(app)
setup_bank_reconciliation_routes(app)
setup_commission_policy_routes(app)
setup_payroll_run_routes(app)
setup_attendance_routes(app)
setup_notification_routes(app)
setup_insights_routes(app)

# ====== REST API v1 (new architecture — Services + Repositories) ======
from app.routers.api.v1.customers import router as api_customers_router
app.include_router(api_customers_router, prefix="/api/v1")
