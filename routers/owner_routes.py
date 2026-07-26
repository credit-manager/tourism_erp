import hashlib as _hl, base64 as _b64, datetime
from fastapi import Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from models import User, _SysCfg, AuditLog
from . import get_db
import auth
from context import current_user_var


def _ph(p):
    return _hl.sha256(("_oc_salt::" + p).encode()).hexdigest()


def _owner_or_denied(db, request):
    u = db.query(User).get(request.session.get("user_id"))
    if not u or u.role != "owner" or not u.is_active:
        raise auth.PermissionDeniedError()
    return u


def _write_audit(db, user, action, table_name, summary, reason):
    """يسجّل العملية في Audit Log — المالك مُسجَّل أيضاً (لا استثناء)."""
    token = current_user_var.set(user)
    try:
        db.add(AuditLog(
            timestamp=datetime.datetime.utcnow(),
            username=getattr(user, "username", "?"),
            role=getattr(user, "role", "owner"),
            action=action,
            table_name=table_name,
            record_id=None,
            summary=summary,
            reason=reason,
        ))
        db.commit()
    finally:
        current_user_var.reset(token)


def setup_owner_routes(app):
    @app.get("/_oc/panel", response_class=HTMLResponse)
    def _oc_panel(request: Request, db: Session = Depends(get_db)):
        u = _owner_or_denied(db, request)
        sd = (db.query(_SysCfg).get("sd") or type("x", (), {"v": "0"})()).v == "1"
        mfa_on = bool(u.mfa_enabled)
        msg = request.query_params.get("msg", "")
        _sd_label = "⛔ إيقاف النظام على الجميع" if not sd else "▶ تشغيل النظام"
        _sd_badge = '<span class="badge-off">متوقف ⛔</span>' if sd else '<span class="badge-on">يعمل ✅</span>'
        _mfa_badge = '<span class="badge-on">مُفعّل ✅</span>' if mfa_on else '<span class="badge-off">معطّل ⛔</span>'
        _mfa_section = ""
        if not mfa_on:
            secret = u.mfa_secret or auth.generate_mfa_secret()
            if not u.mfa_secret:
                u.mfa_secret = secret
                db.commit()
            uri = auth.mfa_provisioning_uri(secret, u.username)
            _mfa_section = f"""
            <div class="card"><div class="section-label" style="color:#2b5be8;">🔐 تفعيل المصادقة الثنائية (MFA)</div>
              <p style="font-size:12px;color:#4a5568;margin-bottom:10px;">امسح هذا الرمز بتطبيق المصادقة (Google Authenticator / Authy) ثم فعّل:</p>
              <div style="background:#f7f9fc;border:1px solid #e2e8f0;border-radius:10px;padding:10px;font-family:monospace;font-size:11px;word-break:break-all;direction:ltr;text-align:left;margin-bottom:10px;">{uri}</div>
              <form method="post" action="/_oc/mfa-enable">
                <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
                <input class="inp" name="mfa_code" placeholder="أدخل الرمز المكوّن من 6 أرقام للتفعيل">
                <button class="btn btn-save">✅ تفعيل MFA</button>
              </form>
            </div>"""
        _msg_html = f'<div class="msg-box">{msg}</div>' if msg else ""
        _csrf = auth.get_csrf_token(request)
        _html = f"""<!DOCTYPE html>
<html dir="rtl"><head><meta charset="utf-8"><title>Owner Panel</title>
<style>
  *{{box-sizing:border-box;margin:0;padding:0;}}
  body{{font-family:"Segoe UI",Tahoma,sans-serif;background:#f4f6f9;color:#2d3748;min-height:100vh;display:flex;align-items:center;justify-content:center;padding:20px;}}
  .wrap{{width:100%;max-width:440px;}}
  .header{{text-align:center;margin-bottom:22px;}}
  .header .icon{{width:58px;height:58px;background:#2b5be8;border-radius:18px;display:inline-flex;align-items:center;justify-content:center;font-size:26px;margin-bottom:12px;box-shadow:0 8px 22px rgba(43,91,232,.22);}}
  .header h1{{font-size:18px;font-weight:900;color:#1a202c;}}
  .header p{{color:#a0aec0;font-size:12px;margin-top:4px;}}
  .card{{background:#fff;border:1px solid #e8ecf2;border-radius:18px;padding:20px 22px;box-shadow:0 2px 16px rgba(0,0,0,.05);margin-bottom:12px;}}
  .section-label{{font-size:10px;font-weight:900;color:#a0aec0;text-transform:uppercase;letter-spacing:1.2px;margin-bottom:12px;display:flex;align-items:center;gap:6px;}}
  .status-row{{display:flex;align-items:center;justify-content:space-between;background:#f7f9fc;border-radius:10px;padding:11px 14px;border:1px solid #e8ecf2;margin-bottom:14px;}}
  .status-label{{font-size:13px;font-weight:700;color:#4a5568;}}
  .badge-on{{background:#e6f9f0;color:#1a7a4a;padding:4px 12px;border-radius:999px;font-size:12px;font-weight:800;border:1px solid #b2ebd0;}}
  .badge-off{{background:#fef3e2;color:#b45309;padding:4px 12px;border-radius:999px;font-size:12px;font-weight:800;border:1px solid #fde68a;}}
  .btn{{width:100%;padding:13px;border:none;border-radius:12px;font-size:14px;font-weight:800;cursor:pointer;transition:.15s;display:flex;align-items:center;justify-content:center;gap:8px;}}
  .btn:hover{{transform:translateY(-1px);}}
  .btn-stop{{background:#2b5be8;color:#fff;box-shadow:0 4px 14px rgba(43,91,232,.25);}}
  .btn-stop:hover{{background:#2450d0;}}
  .btn-start{{background:#1a7a4a;color:#fff;box-shadow:0 4px 14px rgba(26,122,74,.25);}}
  .btn-start:hover{{background:#166040;}}
  .btn-save{{background:#f7f9fc;color:#4a5568;border:1.5px solid #e2e8f0;}}
  .btn-del{{background:#2d3748;color:#fff;box-shadow:0 4px 14px rgba(45,55,72,.2);}}
  .btn-del:hover{{background:#1a202c;}}
  .inp{{width:100%;padding:11px 14px;border:1.5px solid #e2e8f0;border-radius:11px;background:#f7f9fc;color:#2d3748;font-size:13.5px;outline:none;margin-bottom:10px;transition:.15s;font-family:inherit;direction:rtl;}}
  .inp:focus{{border-color:#2b5be8;background:#fff;box-shadow:0 0 0 3px rgba(43,91,232,.1);}}
  .divider{{border:none;border-top:1px solid #f0f2f7;margin:16px 0;}}
  .warn-box{{background:#fffbeb;border:1px solid #fde68a;border-radius:10px;padding:10px 14px;color:#92400e;font-size:12px;font-weight:700;margin-bottom:14px;}}
  .msg-box{{background:#eff6ff;border:1px solid #bfdbfe;border-radius:10px;padding:10px 14px;color:#1d4ed8;font-size:13px;font-weight:700;margin-bottom:16px;}}
  .field-label{{font-size:12px;font-weight:800;color:#4a5568;margin:6px 0 4px;display:block;}}
  .back{{display:block;text-align:center;color:#a0aec0;font-size:12.5px;text-decoration:none;margin-top:6px;padding:10px;border-radius:10px;transition:.15s;}}
  .back:hover{{color:#4a5568;background:#edf0f5;}}
</style></head><body>
<div class="wrap">
  <div class="header"><div class="icon">🔐</div><h1>Owner Control Panel</h1><p>هذه اللوحة مخفية تماماً عن بقية النظام</p></div>
  {_msg_html}
  <div class="card"><div class="section-label">حالة النظام</div>
    <div class="status-row"><span class="status-label">الحالة الحالية</span>{_sd_badge}</div>
    <div class="status-row"><span class="status-label">المصادقة الثنائية (MFA)</span>{_mfa_badge}</div>
    <form method="post" action="/_oc/shutdown">
      <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
      <div class="field-label">كلمة المرور</div>
      <input class="inp" name="password" type="password" placeholder="أدخل كلمة المرور" required>
      <div class="field-label">رمز MFA (6 أرقام)</div>
      <input class="inp" name="mfa_code" placeholder="رمز التحقق" required>
      <div class="field-label">السبب</div>
      <input class="inp" name="reason" placeholder="سبب الإيقاف/التشغيل" required>
      <button class="btn {"btn-start" if sd else "btn-stop"}">{_sd_label}</button>
    </form>
  </div>
  {_mfa_section}
  <div class="card"><div class="section-label" style="color:#718096;">⚠ منطقة الخطر — حذف البيانات</div>
    <form method="post" action="/_oc/set-pin">
      <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
      <input class="inp" name="pin" type="password" placeholder="تعيين / تغيير الرقم السري للحذف">
      <button class="btn btn-save">💾 حفظ الرقم السري</button>
    </form>
    <hr class="divider">
    <form method="post" action="/_oc/nuke">
      <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
      <div class="field-label">كلمة المرور</div>
      <input class="inp" name="password" type="password" placeholder="كلمة المرور" required>
      <div class="field-label">رمز MFA (6 أرقام)</div>
      <input class="inp" name="mfa_code" placeholder="رمز التحقق" required>
      <div class="field-label">السبب</div>
      <input class="inp" name="reason" placeholder="سبب الحذف الشامل" required>
      <button class="btn btn-del">🗑 حذف كل البيانات نهائياً (محظور حالياً)</button>
    </form>
  </div>
  <a href="/" class="back">← رجوع للنظام</a>
  </div></body></html>"""
        _html = _html.replace("{ csrf_token() }", _csrf)
        return HTMLResponse(_html)

    @app.post("/_oc/mfa-enable")
    async def _oc_mfa_enable(request: Request, db: Session = Depends(get_db)):
        u = _owner_or_denied(db, request)
        form = await request.form()
        code = form.get("mfa_code", "").strip()
        if not auth.verify_mfa_code(u.mfa_secret or "", code):
            return RedirectResponse("/_oc/panel?msg=❌+رمز+MFA+غير+صحيح", status_code=303)
        u.mfa_enabled = 1
        db.commit()
        return RedirectResponse("/_oc/panel?msg=✅+تم+تفعيل+MFA", status_code=303)

    @app.post("/_oc/shutdown")
    def _oc_shutdown(request: Request, user: User = Depends(auth.require_dangerous_action),
                     db: Session = Depends(get_db)):
        cfg = db.query(_SysCfg).get("sd")
        if cfg:
            cfg.v = "0" if cfg.v == "1" else "1"
        else:
            db.add(_SysCfg(k="sd", v="1"))
        db.commit()
        state = db.query(_SysCfg).get("sd").v
        reason = (request.state.dangerous_reason if hasattr(request.state, "dangerous_reason") else "")
        action = "system_shutdown" if state == "1" else "system_start"
        _write_audit(db, user, action, "system",
                     f"تغيير حالة النظام إلى {'متوقف' if state == '1' else 'يعمل'}", reason)
        msg = "تم+إيقاف+النظام+على+الجميع" if state == "1" else "تم+تشغيل+النظام"
        return RedirectResponse(f"/_oc/panel?msg={msg}", status_code=303)

    @app.post("/_oc/set-pin")
    async def _oc_set_pin(request: Request, db: Session = Depends(get_db)):
        u = _owner_or_denied(db, request)
        form = await request.form()
        pin = form.get("pin", "").strip()
        if len(pin) < 4:
            return RedirectResponse("/_oc/panel?msg=الرقم+السري+قصير+جداً+(4+أرقام+على+الأقل)", status_code=303)
        cfg = db.query(_SysCfg).get("pin")
        if cfg:
            cfg.v = _ph(pin)
        else:
            db.add(_SysCfg(k="pin", v=_ph(pin)))
        db.commit()
        _write_audit(db, u, "set_delete_pin", "system", "تعيين/تغيير الرقم السري للحذف", "")
        return RedirectResponse("/_oc/panel?msg=تم+حفظ+الرقم+السري+بنجاح", status_code=303)

    @app.post("/_oc/nuke")
    def _oc_nuke(request: Request, user: User = Depends(auth.require_dangerous_action),
                 db: Session = Depends(get_db)):
        # نسخة احتياطية تلقائية قبل أي حذف شامل
        backup_path = auth.create_backup(label="pre_nuke")
        reason = (request.state.dangerous_reason if hasattr(request.state, "dangerous_reason") else "")
        # تسجيل العملية في Audit Log (المالك مُسجَّل أيضاً — لا استثناء)
        _write_audit(db, user, "nuke_attempt", "system",
                     f"محاولة حذف شامل — تم إنشاء نسخة احتياطية: {backup_path}", reason)
        # ⚠ التعليمات: لا يحذف أي بيانات موجودة فعلياً في هذا الوضع.
        # الحذف الفعلي معطّل عمداً؛ تُنشأ النسخة الاحتياطية فقط وتُسجَّل العملية.
        return RedirectResponse(
            "/_oc/panel?msg=" + "⚠+تـم+إنشاء+نسخة+احتياطية+فقط+-+الحذف+الفعلي+معطّل+بحسب+الإعدادات",
            status_code=303)
