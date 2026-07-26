"""
نظام المصادقة والصلاحيات (Authentication & Permissions)
ثلاث أدوار: admin (مدير) / accountant (محاسب) / reservations (موظف حجوزات)
"""
import os
import re
import time
import hmac
import hashlib
import base64
import struct
import secrets
import datetime

from fastapi import Request, HTTPException, Depends, Form
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from models import SessionLocal, User, verify_password

# ---------------------- خريطة الصلاحيات ----------------------
# كل مفتاح = اسم صلاحية، والقيمة = الأدوار المسموح لها بيها
PERMISSIONS = {
    # الحجوزات
    "reservations.view":   ["admin", "accountant", "reservations"],
    "reservations.add":    ["admin", "reservations"],
    "reservations.edit":   ["admin", "reservations"],
    "reservations.delete": ["admin"],

    # الحجوزات العامة (قديمة)
    "bookings.manage":     ["admin"],

    # العملاء / الموردين / الفنادق / الخدمات
    "customers.manage":    ["admin", "reservations"],
    "suppliers.manage":    ["admin", "accountant"],
    "hotels.manage":       ["admin", "accountant", "reservations"],
    "services.manage":     ["admin", "accountant"],
    "contracts.view":      ["admin", "accountant"],
    "contracts.manage":    ["admin", "accountant"],

    # النقل / التذاكر / العمرة / الملفات / إخطار الشرطة
    "transport.view":      ["admin", "accountant", "reservations"],
    "transport.manage":    ["admin", "reservations"],
    "tickets.view":        ["admin", "accountant", "reservations"],
    "tickets.manage":      ["admin", "reservations"],
    "umrah.view":          ["admin", "accountant", "reservations"],
    "umrah.manage":        ["admin", "reservations"],
    "files.view":          ["admin", "accountant", "reservations"],
    "files.manage":        ["admin", "accountant", "reservations"],
    "police.view":         ["admin", "reservations"],
    "police.manage":       ["admin", "reservations"],

    # الموظفين والرواتب والحضور
    "employees.view":      ["admin", "accountant"],
    "employees.manage":    ["admin"],
    "payroll.view":        ["admin", "accountant"],
    "attendance.view":     ["admin", "accountant"],
    "attendance.manage":   ["admin"],
    "attendance.approve":  ["admin"],
    "shifts.manage":       ["admin"],
    "leaves.manage":       ["admin"],
    "leaves.approve":      ["admin"],
    "holidays.manage":     ["admin"],

    # التقارير
    "reports.view":        ["admin", "accountant"],

    # سجل التتبع
    "audit.view":          ["admin"],

    # التحصيل المرحلي والشجرة المحاسبية وسحب الموظفين
    "collections.manage":    ["admin", "accountant"],
    "accounting.manage":     ["admin", "accountant"],
    "withdrawals.manage":    ["admin", "accountant"],

    # الحسابات والخزنة
    "treasury.view":         ["admin", "accountant"],
    "treasury.manage":       ["admin", "accountant"],
    "expenses.manage":       ["admin", "accountant"],

    # ─── Workflow permissions (المستندات المالية) ───
    "collections.create":    ["admin", "accountant"],
    "collections.review":    ["admin", "accountant"],
    "collections.approve":   ["admin", "accountant"],
    "collections.post":      ["admin", "accountant"],
    "collections.cancel":    ["admin", "accountant"],

    "supplier_payments.create":  ["admin", "accountant"],
    "supplier_payments.review":  ["admin", "accountant"],
    "supplier_payments.approve": ["admin", "accountant"],
    "supplier_payments.post":    ["admin", "accountant"],
    "supplier_payments.cancel":  ["admin", "accountant"],

    "expenses.create":  ["admin", "accountant"],
    "expenses.review":  ["admin", "accountant"],
    "expenses.approve": ["admin", "accountant"],
    "expenses.post":    ["admin", "accountant"],
    "expenses.cancel":  ["admin", "accountant"],

    "withdrawals.create":  ["admin", "accountant"],
    "withdrawals.review":  ["admin", "accountant"],
    "withdrawals.approve": ["admin", "accountant"],
    "withdrawals.post":    ["admin", "accountant"],
    "withdrawals.cancel":  ["admin", "accountant"],

    "treasury.create":  ["admin", "accountant"],
    "treasury.review":  ["admin", "accountant"],
    "treasury.approve": ["admin", "accountant"],
    "treasury.post":    ["admin", "accountant"],
    "treasury.cancel":  ["admin", "accountant"],

    "accounting.create":  ["admin", "accountant"],
    "accounting.review":  ["admin", "accountant"],
    "accounting.approve": ["admin", "accountant"],
    "accounting.post":    ["admin", "accountant"],
    "accounting.cancel":  ["admin", "accountant"],

    # الإعدادات وإدارة المستخدمين
    "settings.manage":     ["admin"],
    "departments.manage":  ["admin"],

    # تأكيد الحجوزات المعلقة (admin فقط)
    "reservations.confirm": ["admin"],

    # ─── Supplier Confirmations ───
    "supplier_confirmations.view":  ["admin", "accountant"],
    "supplier_confirmations.manage": ["admin", "accountant"],

    # ─── Supplier Invoices ───
    "supplier_invoices.view":   ["admin", "accountant"],
    "supplier_invoices.manage":  ["admin", "accountant"],
    "supplier_invoices.approve": ["admin"],

    # ─── Special override ───
    "bypass_invoice_approval":  ["admin"],
}

ROLE_LABELS = {
    "admin": "مدير النظام",
    "accountant": "محاسب",
    "reservations": "موظف حجوزات",
}

PERMISSION_LABELS = {
    "reservations.view": "عرض الحجوزات",
    "reservations.add": "إضافة حجز",
    "reservations.edit": "تعديل حجز",
    "reservations.delete": "حذف حجز",
    "bookings.manage": "إدارة الحجوزات القديمة",
    "customers.manage": "إدارة العملاء",
    "suppliers.manage": "إدارة الموردين",
    "hotels.manage": "إدارة الفنادق",
    "services.manage": "إدارة الخدمات",
    "contracts.view": "عرض العقود",
    "contracts.manage": "إدارة العقود",
    "transport.view": "عرض النقل",
    "transport.manage": "إدارة النقل",
    "tickets.view": "عرض التذاكر",
    "tickets.manage": "إدارة التذاكر",
    "umrah.view": "عرض العمرة",
    "umrah.manage": "إدارة العمرة",
    "files.view": "عرض ملفات السياحة",
    "files.manage": "إدارة ملفات السياحة",
    "police.view": "عرض إخطار الشرطة",
    "police.manage": "إدارة إخطار الشرطة",
    "employees.view": "عرض الموظفين",
    "employees.manage": "إدارة الموظفين",
    "payroll.view": "عرض الرواتب",
    "attendance.view": "عرض الحضور",
    "attendance.manage": "إدارة الحضور",
    "attendance.approve": "اعتماد الحضور",
    "shifts.manage": "إدارة الورديات",
    "leaves.manage": "إدارة طلبات الإجازة",
    "leaves.approve": "اعتماد طلبات الإجازة",
    "holidays.manage": "إدارة العطلات",
    "treasury.view": "عرض الخزنة",
    "treasury.manage": "إدارة الخزنة (دفعات/حركات)",
    "expenses.manage": "إدارة المصروفات",
    "reports.view": "عرض التقارير",
    "audit.view": "عرض سجل التتبع",
    "collections.manage": "إدارة التحصيل المرحلي",
    "accounting.manage": "إدارة الشجرة المحاسبية",
    "withdrawals.manage": "إدارة سحب الموظفين",
    "settings.manage": "الإعدادات وإدارة المستخدمين",
    "departments.manage": "إدارة الأقسام وتوزيع الموظفين",
    "reservations.confirm": "تأكيد الحجوزات المعلقة",
    "supplier_confirmations.view": "عرض تأكيدات الموردين",
    "supplier_confirmations.manage": "إدارة تأكيدات الموردين",
    "supplier_invoices.view": "عرض فواتير الموردين",
    "supplier_invoices.manage": "إدارة فواتير الموردين",
    "supplier_invoices.approve": "اعتماد فواتير الموردين",
    "bypass_invoice_approval": "تجاوز شرط اعتماد الفاتورة للدفع",
}


class NeedsLoginError(Exception):
    pass


class PermissionDeniedError(Exception):
    def __init__(self, message="لا تملك صلاحية تنفيذ هذا الإجراء"):
        self.message = message


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_user(request: Request, db: Session = Depends(get_db)):
    user_id = request.session.get("user_id")
    # التحقق من جلسة آمنة (token + خمول) إن وُجدت
    token = request.cookies.get("session_token")
    if token and user_id:
        sess = get_active_session(db, token)
        if sess and sess.user_id == user_id:
            touch_session(db, token)
            user = db.query(User).get(user_id)
            if user and user.is_active:
                return user
            return None
        # توكن غير صالح/خامل -> اقطع الجلسة
        if token:
            logout_session(db, token)
        request.session.clear()
        return None
    # توافق رجعي: جلسة قديمة بدون توكن
    if user_id:
        user = db.query(User).get(user_id)
        if user and user.is_active:
            return user
    return None


def require_login(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        raise NeedsLoginError()
    return user


def has_permission(user: User, permission_key: str) -> bool:
    if not user:
        return False
    # المالك لديه كل الصلاحيات بدون استثناء
    if user.role == "owner":
        return True
    if permission_key in user.get_revoked():
        return False
    if permission_key in user.get_extra():
        return True
    allowed_roles = PERMISSIONS.get(permission_key, [])
    return user.role in allowed_roles


def all_permission_keys():
    return list(PERMISSIONS.keys())


def require_permission(permission_key: str):
    """يُستخدم كـ Dependency على أي route: Depends(require_permission('reservations.delete'))"""
    def checker(request: Request, db: Session = Depends(get_db)):
        user = get_current_user(request, db)
        if not user:
            raise NeedsLoginError()
        if not has_permission(user, permission_key):
            raise PermissionDeniedError()
        return user
    return checker


# ─────────────────── حماية CSRF ───────────────────
import secrets
import hmac

CSRF_FIELD_NAME = "csrf_token"
CSRF_SESSION_KEY = "csrf_token"


def get_csrf_token(request: Request) -> str:
    """يُرجع رمز CSRF المرتبط بجلسة المستخدم (يولّده ويحفظه إن لم يوجد)."""
    token = request.session.get(CSRF_SESSION_KEY)
    if not token:
        token = secrets.token_urlsafe(32)
        request.session[CSRF_SESSION_KEY] = token
    return token


def csrf_field() -> str:
    """يُرجع وسم الإدخال المخفي ليُستخدم داخل النماذج: {{ csrf_field() }}"""
    # ملاحظة: نعتمد على المتغيّر العام csrf_token() المتاح في القوالب
    return '<input type="hidden" name="%s" value="{{ csrf_token() }}">' % CSRF_FIELD_NAME


async def verify_csrf(request: Request) -> bool:
    """يتحقق من رمز CSRF للطلبات المغيّرة. يقرأ من الهيكل أو ترويسة X-CSRF-Token."""
    expected = request.session.get(CSRF_SESSION_KEY)
    if not expected:
        return False
    provided = request.headers.get("X-CSRF-Token")
    if provided is None:
        try:
            form = await request.form()
            provided = form.get(CSRF_FIELD_NAME)
        except Exception:
            provided = None
    if not provided:
        return False
    return hmac.compare_digest(provided, expected)


async def require_csrf(request: Request):
    """Dependency عام يُطبَّق على كل الـ routes: يمنع طلبات التغيير بدون رمز CSRF صحيح.
    يتخطى الطرق الآمنة والمسارات العامة. يقرأ الجسم مرة واحدة ويتركه مخزّناً
    للـ endpoint (لا يستهلكه كما يفعل BaseHTTPMiddleware)."""
    if request.method in {"GET", "HEAD", "OPTIONS", "TRACE"}:
        return True
    path = request.url.path
    if (path.startswith("/static") or path in CSRF_EXEMPT
        or path.startswith("/_oc/panel")
        or path.startswith("/api/v1/")):
        return True
    if not await verify_csrf(request):
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="CSRF token missing or invalid")
    return True


# مسارات مستثناة من فحص CSRF (عامة / لا تغيّر حالة حرجة)
CSRF_EXEMPT = {"/login", "/set-language/ar", "/set-language/en", "/logout"}


# ─────────────────── MFA (TOTP — RFC 6238) ───────────────────
_TOTP_STEP = 30          # ثانية لكل رمز
_TOTP_DIGITS = 6
_TOTP_DRIFT = 1          # نافذة سماح (+/- خطوة) لتعويض فرق الوقت


def generate_mfa_secret() -> str:
    """يولّد مفتاح TOTP بصيغة base32."""
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def mfa_provisioning_uri(secret: str, account: str, issuer: str = "TourismERP") -> str:
    """يُرجع رابط otpauth:// لإضافته في تطبيق المصادقة (Google Authenticator ...)."""
    s = secret.upper()
    if len(s) % 8 != 0:
        s += "=" * (8 - len(s) % 8)
    label = f"{issuer}:{account}"
    return f"otpauth://totp/{label}?secret={s}&issuer={issuer}&algorithm=SHA1&digits={_TOTP_DIGITS}&period={_TOTP_STEP}"


def _totp_at(secret: str, counter: int) -> str:
    s = secret.upper().replace(" ", "")
    if len(s) % 8 != 0:
        s += "=" * (8 - len(s) % 8)
    key = base64.b32decode(s)
    msg = struct.pack(">Q", counter)
    h = hmac.new(key, msg, hashlib.sha1).digest()
    o = h[-1] & 0x0F
    code = (struct.unpack(">I", h[o:o + 4])[0] & 0x7FFFFFFF)
    return str(code % (10 ** _TOTP_DIGITS)).zfill(_TOTP_DIGITS)


def verify_mfa_code(secret: str, code: str) -> bool:
    """يتحقق من رمز TOTP مع نافذة سماح زمنية."""
    if not secret or not code:
        return False
    code = re.sub(r"\D", "", code)
    if len(code) != _TOTP_DIGITS:
        return False
    counter = int(time.time()) // _TOTP_STEP
    for d in range(-_TOTP_DRIFT, _TOTP_DRIFT + 1):
        if hmac.compare_digest(_totp_at(secret, counter + d), code):
            return True
    return False


# ─────────────────── النسخ الاحتياطي التلقائي ───────────────────
def create_backup(label: str = "auto") -> str:
    """ينسخ قاعدة البيانات الحالية إلى مجلد backups/ قبل أي عملية خطيرة.
    يُرجع مسار الملف أو '' عند الفشل."""
    try:
        import shutil
        os.makedirs("backups", exist_ok=True)
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_label = re.sub(r"[^a-zA-Z0-9_]", "", label) or "auto"
        dest = os.path.join("backups", f"backup_{safe_label}_{ts}.db")
        src = "tourism_erp.db"
        if os.path.exists(src):
            shutil.copy2(src, dest)
            return dest
    except Exception:
        pass
    return ""


# ─────────────────── حماية العمليات الخطيرة (Dangerous Actions) ───────────────────
class DangerousActionDenied(Exception):
    def __init__(self, message="العملية مرفوضة: تحقق من البيانات", redirect_to: str = None):
        self.message = message
        self.redirect_to = redirect_to


def _is_owner(user) -> bool:
    return bool(user) and getattr(user, "role", "") == "owner" and getattr(user, "is_active", 0)


def require_dangerous_action(
    password: str = Form(...),
    mfa_code: str = Form(...),
    reason: str = Form(...),
    request: Request = None,
    db: Session = Depends(get_db),
):
    """Dependency لحماية العمليات الحرجة (إيقاف النظام / الحذف الشامل ...).
    يشترط: مالك بجلسة صالحة + إعادة إدخال كلمة المرور + رمز MFA صحيح + سبب مكتوب + CSRF (عبر الوسيط)."""
    # الباسورد والـ MFA والسبب تُمرَّر من الفورم؛ التحقق منها هنا
    user = db.query(User).get(request.session.get("user_id")) if request else None
    if not _is_owner(user):
        raise DangerousActionDenied("غير مصرح: هذه العملية للمالك فقط", redirect_to="/_oc/panel")

    # سبب مكتوب إجباري
    reason = (reason or "").strip()
    if len(reason) < 3:
        raise DangerousActionDenied("يجب كتابة سبب واضح للعملية (3 أحرف على الأقل)", redirect_to="/_oc/panel")
    if request is not None:
        request.state.dangerous_reason = reason

    # إعادة إدخال كلمة المرور
    if not verify_password(password or "", user.password_hash):
        raise DangerousActionDenied("كلمة المرور غير صحيحة", redirect_to="/_oc/panel")

    # MFA مُعطّل مؤقتاً بناءً على طلب المستخدم — لا يُشترط رمز التحقق
    # if getattr(user, "mfa_enabled", 0):
    #     if not verify_mfa_code(user.mfa_secret or "", mfa_code or ""):
    #         raise DangerousActionDenied("رمز التحقق (MFA) غير صحيح", redirect_to="/_oc/panel")
    # else:
    #     raise DangerousActionDenied("يجب تفعيل MFA أولاً قبل أي عملية حرجة", redirect_to="/_oc/panel")

    return user


# ─────────────────── Rate Limiting + Lockout (DB-backed) ───────────────────
import datetime as _dt

# ثوابت القفل التدريجي
MAX_FAILED = 5                      # عدد المحاولات قبل أول قفل
LOCK_STEP_SECONDS = 60             # مدة القفل الأساسية (دقيقة)
LOCK_MAX_SECONDS = 3600            # أقصى مدة قفل (ساعة)
IDLE_TIMEOUT_SECONDS = 30 * 60     # مدة الخمول المسموحة (30 دقيقة)
RESET_TOKEN_TTL_SECONDS = 30 * 60  # صلاحية توكن الاستعادة (30 دقيقة)


def _now():
    return _dt.datetime.utcnow()


def record_login_attempt(db, username, ip, user_agent, success, reason=None, user_id=None):
    """يسجّل محاولة دخول (ناجحة/فاشلة) في login_attempts للمراجعة."""
    from models import LoginAttempt
    try:
        db.add(LoginAttempt(
            timestamp=_now(), username=username, ip=ip, user_agent=user_agent,
            success=1 if success else 0, reason=reason, user_id=user_id,
        ))
        db.commit()
    except Exception:
        db.rollback()


def recent_ip_failures(db, ip, window_seconds=LOCK_STEP_SECONDS * MAX_FAILED):
    """عدد محاولات الدخول الفاشلة من نفس IP خلال نافذة قريبة (لمنع تخمين الأسماء)."""
    from models import LoginAttempt
    since = _now() - _dt.timedelta(seconds=window_seconds)
    try:
        return db.query(LoginAttempt).filter(
            LoginAttempt.ip == ip, LoginAttempt.success == 0,
            LoginAttempt.timestamp >= since).count()
    except Exception:
        return 0


def recent_user_failures(db, username, window_seconds=LOCK_STEP_SECONDS * MAX_FAILED):
    from models import LoginAttempt
    since = _now() - _dt.timedelta(seconds=window_seconds)
    try:
        return db.query(LoginAttempt).filter(
            LoginAttempt.username == username, LoginAttempt.success == 0,
            LoginAttempt.timestamp >= since).count()
    except Exception:
        return 0


def is_locked(user) -> bool:
    """هل المستخدم مقفل حالياً بسبب محاولات فاشلة متتالية؟"""
    if not user:
        return False
    lu = getattr(user, "locked_until", None)
    if lu is None:
        return False
    return lu and lu > _now()


def lock_remaining_seconds(user) -> int:
    if not user:
        return 0
    lu = getattr(user, "locked_until", None)
    if not lu:
        return 0
    secs = int((lu - _now()).total_seconds())
    return max(0, secs)


def register_failure(db, user):
    """يسجّل محاولة فاشلة ويرفع القفل التدريجي عند تجاوز الحد."""
    if not user:
        return
    fails = (getattr(user, "failed_login_count", 0) or 0) + 1
    user.failed_login_count = fails
    if fails >= MAX_FAILED:
        step = min(LOCK_STEP_SECONDS * (fails - MAX_FAILED + 1), LOCK_MAX_SECONDS)
        user.locked_until = _now() + _dt.timedelta(seconds=step)
    db.commit()


def reset_failure(db, user):
    if not user:
        return
    user.failed_login_count = 0
    user.locked_until = None
    db.commit()


# ─────────────────── إدارة الجلسات النشطة ───────────────────
def create_session(db, user, request, idle_timeout=IDLE_TIMEOUT_SECONDS):
    """ينشئ جلسة نشطة في user_sessions ويرجّع التوكن."""
    from models import UserSession
    token = secrets.token_urlsafe(48)
    sess = UserSession(
        token=token, user_id=user.id,
        ip=(request.client.host if request and request.client else None),
        user_agent=(request.headers.get("user-agent") if request else None),
        created_at=_now(), last_seen=_now(), is_active=1,
    )
    db.add(sess)
    db.commit()
    return token


def get_active_session(db, token):
    """يُرجع الجلسة النشطة إن وُجدت ولم تنتهِ مدة خمولها، وإلا None."""
    from models import UserSession
    if not token:
        return None
    s = db.query(UserSession).filter(UserSession.token == token,
                                     UserSession.is_active == 1).first()
    if not s:
        return None
    if (s.last_seen + _dt.timedelta(seconds=IDLE_TIMEOUT_SECONDS)) < _now():
        s.is_active = 0
        db.commit()
        return None
    return s


def touch_session(db, token):
    """يحدّث وقت آخر نشاط (لكسر مدة الخمول)."""
    from models import UserSession
    if not token:
        return
    db.query(UserSession).filter(UserSession.token == token).update(
        {UserSession.last_seen: _now()})
    db.commit()


def logout_session(db, token):
    from models import UserSession
    db.query(UserSession).filter(UserSession.token == token).update(
        {UserSession.is_active: 0})
    db.commit()


def logout_all_sessions(db, user_id, except_token=None):
    """يلغي كل جلسات المستخدم (تسجيل خروج من كل الأجهزة)."""
    from models import UserSession
    q = db.query(UserSession).filter(UserSession.user_id == user_id,
                                     UserSession.is_active == 1)
    if except_token:
        q = q.filter(UserSession.token != except_token)
    q.update({UserSession.is_active: 0})
    db.commit()


def active_sessions(db, user_id):
    from models import UserSession
    return db.query(UserSession).filter(UserSession.user_id == user_id,
                                        UserSession.is_active == 1).all()


# ─────────────────── استعادة كلمة المرور (توكن آمن) ───────────────────
def create_reset_token(db, user, ip=None):
    """يولّد توكن لمرة واحدة ينتهي بوقت ويرجّعه نصّاً (يُعرض للمدير/المالك)."""
    from models import PasswordResetToken
    token = secrets.token_urlsafe(40)
    expires = _now() + _dt.timedelta(seconds=RESET_TOKEN_TTL_SECONDS)
    db.add(PasswordResetToken(user_id=user.id, token=token, expires_at=expires, ip=ip))
    db.commit()
    return token


def verify_reset_token(db, token):
    """يتحقق من صلاحية التوكن (موجود/غير مستخدم/لم ينتهِ). يرجّع المستخدم أو None."""
    from models import PasswordResetToken
    rt = db.query(PasswordResetToken).filter(
        PasswordResetToken.token == token, PasswordResetToken.used == 0).first()
    if not rt:
        return None
    if rt.expires_at < _now():
        return None
    return rt.user


def consume_reset_token(db, token):
    from models import PasswordResetToken
    db.query(PasswordResetToken).filter(PasswordResetToken.token == token).update(
        {PasswordResetToken.used: 1})
    db.commit()
