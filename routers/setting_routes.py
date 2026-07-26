import json
from fastapi import Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from currency_utils import D, DECIMAL_ZERO

from models import User, Employee, Currency, AuditLog, Department, hash_password
from . import templates, get_db
import auth


def setup_setting_routes(app):
    @app.get("/settings", response_class=HTMLResponse)
    def settings_page(request: Request, db: Session = Depends(get_db),
                      user=Depends(auth.require_permission("settings.manage"))):
        users = db.query(User).filter(User.role != "owner").all()
        employees = db.query(Employee).all()
        currencies = db.query(Currency).all()
        return templates.TemplateResponse(request, "settings.html", {
            "request": request, "page_title": "الإعدادات - المستخدمين والصلاحيات", "active": "settings",
            "users": users, "employees": employees, "currencies": currencies,
        })

    @app.post("/settings/users/add")
    def add_user(username: str = Form(...), password: str = Form(...), full_name: str = Form(""),
                 role: str = Form("reservations"), employee_id: int = Form(None),
                 db: Session = Depends(get_db), user=Depends(auth.require_permission("settings.manage"))):
        if db.query(User).filter(User.username == username).first():
            return RedirectResponse("/settings?error=اسم+المستخدم+موجود+مسبقاً", status_code=303)
        db.add(User(username=username, password_hash=hash_password(password), full_name=full_name,
                    role=role, employee_id=employee_id or None, is_active=1,
                    extra_permissions="[]", revoked_permissions="[]"))
        db.commit()
        return RedirectResponse("/settings", status_code=303)

    @app.post("/settings/users/{user_id}/edit")
    def edit_user(user_id: int, full_name: str = Form(""), role: str = Form("reservations"),
                  employee_id: int = Form(None), is_active: int = Form(1), password: str = Form(""),
                  db: Session = Depends(get_db), user=Depends(auth.require_permission("settings.manage"))):
        u = db.query(User).get(user_id)
        if u and u.role != "owner":
            u.full_name, u.role, u.employee_id, u.is_active = full_name, role, employee_id or None, is_active
            if password:
                u.password_hash = hash_password(password)
            db.commit()
        return RedirectResponse("/settings", status_code=303)

    @app.post("/settings/users/{user_id}/delete")
    def delete_user(user_id: int, request: Request, db: Session = Depends(get_db),
                    user=Depends(auth.require_permission("settings.manage"))):
        if request.session.get("user_id") == user_id:
            return RedirectResponse("/settings?error=لا+يمكنك+حذف+حسابك+الحالي", status_code=303)
        u = db.query(User).get(user_id)
        if u and u.role != "owner":
            db.delete(u)
            db.commit()
        return RedirectResponse("/settings", status_code=303)

    @app.get("/settings/users/{user_id}/permissions", response_class=HTMLResponse)
    def user_permissions_page(user_id: int, request: Request, db: Session = Depends(get_db),
                              user=Depends(auth.require_permission("settings.manage"))):
        target = db.query(User).get(user_id)
        if not target:
            return RedirectResponse("/settings", status_code=303)
        role_defaults = {key: (target.role in roles) for key, roles in auth.PERMISSIONS.items()}
        extra = target.get_extra()
        revoked = target.get_revoked()
        effective = {}
        for key in auth.PERMISSIONS:
            if key in revoked: effective[key] = False
            elif key in extra: effective[key] = True
            else: effective[key] = role_defaults[key]
        return templates.TemplateResponse(request, "user_permissions.html", {
            "request": request, "page_title": f"صلاحيات المستخدم - {target.username}", "active": "settings",
            "target": target, "role_defaults": role_defaults, "effective": effective,
        })

    @app.post("/settings/users/{user_id}/permissions")
    async def update_user_permissions(user_id: int, request: Request, db: Session = Depends(get_db),
                                      user=Depends(auth.require_permission("settings.manage"))):
        target = db.query(User).get(user_id)
        if not target:
            return RedirectResponse("/settings", status_code=303)
        form = await request.form()
        checked_keys = set(form.getlist("permissions"))
        role_defaults = {key: (target.role in roles) for key, roles in auth.PERMISSIONS.items()}
        extra, revoked = [], []
        for key in auth.PERMISSIONS:
            is_checked = key in checked_keys
            default = role_defaults[key]
            if is_checked and not default: extra.append(key)
            elif not is_checked and default: revoked.append(key)
        target.extra_permissions = json.dumps(extra)
        target.revoked_permissions = json.dumps(revoked)
        db.commit()
        return RedirectResponse(f"/settings/users/{user_id}/permissions?saved=1", status_code=303)

    @app.get("/settings/audit-log", response_class=HTMLResponse)
    def audit_log_page(request: Request, db: Session = Depends(get_db),
                       user=Depends(auth.require_permission("audit.view"))):
        logs = db.query(AuditLog).filter(AuditLog.role != "owner").order_by(AuditLog.id.desc()).limit(300).all()
        return templates.TemplateResponse(request, "audit_log.html", {
            "request": request, "page_title": "سجل تتبع العمليات (Audit Log)", "active": "audit", "logs": logs,
        })

    # ─── Currencies ────────────────────────────────────
    @app.post("/settings/currencies/add")
    def add_currency(code: str = Form(...), name: str = Form(""), symbol: str = Form(""),
                     exchange_rate: float = Form(1.0), db: Session = Depends(get_db),
                     user=Depends(auth.require_permission("settings.manage"))):
        if db.query(Currency).filter(Currency.code == code).first():
            return RedirectResponse("/settings?error=العملة+موجودة+مسبقاً", status_code=303)
        db.add(Currency(code=code.upper(), name=name, symbol=symbol, exchange_rate=D(exchange_rate), is_base=0))
        db.commit()
        return RedirectResponse("/settings", status_code=303)

    @app.post("/settings/currencies/{currency_id}/set-base")
    def set_base_currency(currency_id: int, db: Session = Depends(get_db),
                          user=Depends(auth.require_permission("settings.manage"))):
        for c in db.query(Currency).all():
            c.is_base = 1 if c.id == currency_id else 0
            if c.id == currency_id: c.exchange_rate = D(1)
        db.commit()
        return RedirectResponse("/settings", status_code=303)

    @app.post("/settings/currencies/{currency_id}/edit")
    def edit_currency(currency_id: int, name: str = Form(""), symbol: str = Form(""),
                      exchange_rate: float = Form(1.0), db: Session = Depends(get_db),
                      user=Depends(auth.require_permission("settings.manage"))):
        c = db.query(Currency).get(currency_id)
        if c and not c.is_base:
            c.name, c.symbol, c.exchange_rate = name, symbol, D(exchange_rate)
            db.commit()
        return RedirectResponse("/settings", status_code=303)

    @app.post("/settings/currencies/{currency_id}/delete")
    def delete_currency(currency_id: int, db: Session = Depends(get_db),
                        user=Depends(auth.require_permission("settings.manage"))):
        c = db.query(Currency).get(currency_id)
        if c and not c.is_base:
            db.delete(c)
            db.commit()
        return RedirectResponse("/settings", status_code=303)

    # ===== الأقسام (Departments) =====

    @app.get("/settings/departments", response_class=HTMLResponse)
    def departments_page(request: Request, db: Session = Depends(get_db),
                         user=Depends(auth.require_permission("departments.manage"))):
        departments = db.query(Department).order_by(Department.name).all()
        unassigned = db.query(Employee).filter(Employee.department_id == None).all()
        employees = db.query(Employee).all()
        return templates.TemplateResponse(request, "departments.html", {
            "request": request, "page_title": "الأقسام - Departments", "active": "departments",
            "departments": departments, "unassigned": unassigned, "employees": employees,
        })

    @app.post("/settings/departments/add")
    def add_department(name: str = Form(...), name_en: str = Form(""),
                       manager_id: str = Form(""), notes: str = Form(""),
                       db: Session = Depends(get_db),
                       user=Depends(auth.require_permission("departments.manage"))):
        d = Department(
            name=name.strip(), name_en=(name_en.strip() or None),
            manager_id=int(manager_id) if manager_id else None,
            notes=notes.strip() or None,
        )
        db.add(d)
        db.commit()
        return RedirectResponse("/settings/departments", status_code=303)

    @app.post("/settings/departments/{department_id}/edit")
    def edit_department(department_id: int, name: str = Form(...), name_en: str = Form(""),
                        manager_id: str = Form(""), notes: str = Form(""),
                        db: Session = Depends(get_db),
                        user=Depends(auth.require_permission("departments.manage"))):
        d = db.query(Department).get(department_id)
        if d:
            d.name = name.strip()
            d.name_en = name_en.strip() or None
            d.manager_id = int(manager_id) if manager_id else None
            d.notes = notes.strip() or None
            db.commit()
        return RedirectResponse("/settings/departments", status_code=303)

    @app.post("/settings/departments/{department_id}/delete")
    def delete_department(department_id: int, db: Session = Depends(get_db),
                          user=Depends(auth.require_permission("departments.manage"))):
        d = db.query(Department).get(department_id)
        if d:
            # منسيبش الموظفين معلّقين على قسم محذوف — نرجعهم "بدون قسم"
            for emp in db.query(Employee).filter(Employee.department_id == department_id).all():
                emp.department_id = None
            db.delete(d)
            db.commit()
        return RedirectResponse("/settings/departments", status_code=303)

    @app.post("/settings/departments/assign")
    def assign_employee_department(employee_id: int = Form(...),
                                   department_id: str = Form(""),
                                   db: Session = Depends(get_db),
                                   user=Depends(auth.require_permission("departments.manage"))):
        emp = db.query(Employee).get(employee_id)
        if emp:
            emp.department_id = int(department_id) if department_id else None
            db.commit()
        return RedirectResponse("/settings/departments", status_code=303)

    # ===== إعدادات القائمة الجانبية: الاتجاه + الإظهار/الإخفاء =====

    @app.get("/settings/menu-config", response_class=HTMLResponse)
    def menu_config_page(request: Request, user=Depends(auth.require_permission("settings.manage"))):
        from menu_config import MENU_ITEMS_REGISTRY, get_menu_orientation, get_hidden_menu_items
        return templates.TemplateResponse(request, "menu_config.html", {
            "request": request, "page_title": "إعدادات القائمة - Menu Settings", "active": "menu_config",
            "items": MENU_ITEMS_REGISTRY,
            "orientation": get_menu_orientation(),
            "hidden": get_hidden_menu_items(),
        })

    @app.post("/settings/menu-config")
    async def save_menu_config(request: Request, orientation: str = Form("vertical"),
                               user=Depends(auth.require_permission("settings.manage"))):
        from menu_config import set_menu_orientation, set_hidden_menu_items, MENU_ITEMS_REGISTRY
        form = await request.form()
        valid_keys = {k for k, _, _ in MENU_ITEMS_REGISTRY}
        # أي عنصر متبعتش قيمته "on" في الفورم معناه اتشال التيك بتاعه = مخفي
        visible_keys = {k for k in valid_keys if form.get(f"visible_{k}") == "on"}
        hidden_keys = valid_keys - visible_keys
        set_menu_orientation(orientation)
        set_hidden_menu_items(list(hidden_keys))
        return RedirectResponse("/settings/menu-config?saved=1", status_code=303)
