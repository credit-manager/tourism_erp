import datetime
from fastapi import Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import func
from currency_utils import D, DECIMAL_ZERO

from models import (
    Employee, Reservation, Attendance, EmployeeWithdrawal,
    TreasuryAccount, TreasuryTransaction,
)
from . import templates, get_db, _employee_period_earnings, paginate, pagination_ctx
import auth


def setup_employee_routes(app):
    # ─── Employees ─────────────────────────────────────
    @app.get("/employees", response_class=HTMLResponse)
    def employees_page(request: Request, db: Session = Depends(get_db), page: int = 1,
                       user=Depends(auth.require_permission("employees.view"))):
        all_employees = db.query(Employee).all()
        commissions = {}
        counts = {}
        for emp in all_employees:
            commissions[emp.id] = sum(D(r.employee_commission) for r in emp.reservations)
            counts[emp.id] = len(emp.reservations)
        employees, pg, tp, tt = paginate(db.query(Employee).order_by(Employee.id.desc()), page)
        return templates.TemplateResponse(request, "employees.html", {
            "request": request, "page_title": "الموظفين (Employees)", "active": "employees",
            "employees": employees, "commissions": commissions, "counts": counts,
            "p": pagination_ctx(pg, tp, tt), "base_url": f"/employees?page={pg}",
        })

    @app.post("/employees/add")
    def add_employee(name: str = Form(...), salary: float = Form(0), commission_rate: float = Form(0),
                     db: Session = Depends(get_db), user=Depends(auth.require_permission("employees.manage"))):
        db.add(Employee(name=name, salary=D(salary), commission_rate=D(commission_rate)))
        db.commit()
        return RedirectResponse("/employees", status_code=303)

    @app.post("/employees/quick-add")
    async def quick_add_employee(request: Request, db: Session = Depends(get_db),
                                  user=Depends(auth.require_permission("reservations.add"))):
        form = await request.form()
        name = (form.get("name") or "").strip()
        phone = (form.get("phone") or "").strip()
        role = (form.get("role") or "").strip()
        if not name:
            return JSONResponse({"ok": False, "error": "اسم الموظف مطلوب."}, status_code=400)
        try:
            existing = db.query(Employee).filter(func.lower(Employee.name) == name.lower()).first()
            if existing:
                if phone and hasattr(Employee, "phone"):
                    existing.phone = phone
                    db.commit()
                    db.refresh(existing)
                return {"ok": True, "id": existing.id, "name": existing.name,
                        "phone": getattr(existing, "phone", ""), "existing": True}
            employee_data = {"name": name}
            if hasattr(Employee, "phone"): employee_data["phone"] = phone
            if hasattr(Employee, "role"): employee_data["role"] = role
            if hasattr(Employee, "salary"): employee_data["salary"] = 0
            if hasattr(Employee, "commission_rate"): employee_data["commission_rate"] = 0
            emp = Employee(**employee_data)
            db.add(emp)
            db.commit()
            db.refresh(emp)
            return {"ok": True, "id": emp.id, "name": emp.name,
                    "phone": getattr(emp, "phone", ""), "existing": False}
        except Exception as e:
            db.rollback()
            return JSONResponse({"ok": False, "error": f"حصل خطأ أثناء إنشاء الموظف: {str(e)}"}, status_code=500)

    @app.post("/employees/{employee_id}/edit")
    def edit_employee(employee_id: int, name: str = Form(...), salary: float = Form(0), commission_rate: float = Form(0),
                      db: Session = Depends(get_db), user=Depends(auth.require_permission("employees.manage"))):
        e = db.query(Employee).get(employee_id)
        if e:
            e.name, e.salary, e.commission_rate = name, D(salary), D(commission_rate)
            db.commit()
        return RedirectResponse("/employees", status_code=303)

    @app.post("/employees/{employee_id}/delete")
    def delete_employee(employee_id: int, db: Session = Depends(get_db),
                        user=Depends(auth.require_permission("employees.manage"))):
        e = db.query(Employee).get(employee_id)
        if e:
            db.delete(e)
            db.commit()
        return RedirectResponse("/employees", status_code=303)

    @app.get("/employees/{employee_id}", response_class=HTMLResponse)
    def employee_detail_page(employee_id: int, request: Request, db: Session = Depends(get_db),
                              user=Depends(auth.require_permission("employees.view"))):
        employee = db.query(Employee).get(employee_id)
        reservations = db.query(Reservation).filter(Reservation.employee_id == employee_id).order_by(Reservation.id.desc()).all()
        total_commission = sum(D(r.employee_commission) for r in reservations)
        today = datetime.date.today()
        month_start = today.replace(day=1)
        month_attendance = db.query(Attendance).filter(
            Attendance.employee_id == employee_id, Attendance.date >= month_start, Attendance.date <= today
        ).all()
        present_days = sum(1 for a in month_attendance if a.status == "present")
        absent_days = sum(1 for a in month_attendance if a.status == "absent")
        leave_days = sum(1 for a in month_attendance if a.status == "leave")
        return templates.TemplateResponse(request, "employee_detail.html", {
            "request": request, "page_title": f"تفاصيل الموظف - {employee.name}" if employee else "الموظف",
            "active": "employees", "employee": employee, "reservations": reservations,
            "total_commission": total_commission,
            "present_days": present_days, "absent_days": absent_days, "leave_days": leave_days,
        })

    # ─── Payroll ───────────────────────────────────────
    @app.get("/payroll", response_class=HTMLResponse)
    def payroll_page(request: Request, month: str = None, db: Session = Depends(get_db),
                     user=Depends(auth.require_permission("payroll.view"))):
        today = datetime.date.today()
        if not month:
            month = today.strftime("%Y-%m")
        year, mon = map(int, month.split("-"))
        period_start = datetime.date(year, mon, 1)
        period_end = (datetime.date(year, mon + 1, 1) - datetime.timedelta(days=1)) if mon < 12 else datetime.date(year, 12, 31)
        employees = db.query(Employee).all()
        payroll_rows = []
        for emp in employees:
            month_commission = _employee_period_earnings(db, emp.id, period_start, period_end)
            reservations_count = db.query(Reservation).filter(
                Reservation.created_date >= period_start, Reservation.created_date <= period_end,
            ).filter(
                (Reservation.employee_id == emp.id) | (Reservation.travel_agent_id == emp.id) | (Reservation.sales_rep_id == emp.id)
            ).count()
            withdrawn = D(db.query(func.coalesce(func.sum(EmployeeWithdrawal.amount), 0)).filter(
                EmployeeWithdrawal.employee_id == emp.id,
                EmployeeWithdrawal.date >= period_start, EmployeeWithdrawal.date <= period_end,
            ).scalar())
            total_salary = D(emp.salary) + month_commission
            payroll_rows.append({
                "employee": emp, "reservations_count": reservations_count,
                "commission": month_commission, "total_salary": total_salary,
                "withdrawn": withdrawn, "net_due": total_salary - withdrawn,
            })
        grand_total = sum(D(row["total_salary"]) for row in payroll_rows)
        return templates.TemplateResponse(request, "payroll.html", {
            "request": request, "page_title": "الرواتب الشهرية (Payroll)", "active": "payroll",
            "payroll_rows": payroll_rows, "selected_month": month, "grand_total": grand_total,
        })

    # ─── Withdrawals ───────────────────────────────────
    @app.get("/withdrawals", response_class=HTMLResponse)
    def withdrawals_page(request: Request, db: Session = Depends(get_db),
                         user=Depends(auth.require_permission("withdrawals.manage"))):
        employees = db.query(Employee).all()
        withdrawals = db.query(EmployeeWithdrawal).order_by(EmployeeWithdrawal.id.desc()).all()
        accounts = db.query(TreasuryAccount).all()
        today = datetime.date.today()
        month_start = today.replace(day=1)
        employee_summaries = []
        for emp in employees:
            earned = _employee_period_earnings(db, emp.id, month_start, today)
            withdrawn = D(db.query(func.coalesce(func.sum(EmployeeWithdrawal.amount), 0)).filter(
                EmployeeWithdrawal.employee_id == emp.id, EmployeeWithdrawal.date >= month_start,
            ).scalar())
            max_allowed = earned if today.day > 15 else earned * D('0.5')
            employee_summaries.append({
                "employee": emp, "earned": earned, "withdrawn": withdrawn,
                "max_allowed": max_allowed, "available": max(DECIMAL_ZERO, max_allowed - withdrawn),
            })
        return templates.TemplateResponse(request, "withdrawals.html", {
            "request": request, "page_title": "سحب الموظفين من الخزنة", "active": "withdrawals",
            "withdrawals": withdrawals, "accounts": accounts, "employee_summaries": employee_summaries,
            "today_day": today.day,
        })

    @app.post("/withdrawals/add")
    def add_withdrawal(employee_id: int = Form(...), amount: float = Form(...), account_id: int = Form(None),
                       withdrawal_type: str = Form("advance"), notes: str = Form(""),
                       db: Session = Depends(get_db), user=Depends(auth.require_permission("withdrawals.manage"))):
        today = datetime.date.today()
        d_amount = D(amount)
        month_start = today.replace(day=1)
        earned = _employee_period_earnings(db, employee_id, month_start, today)
        withdrawn_so_far = D(db.query(func.coalesce(func.sum(EmployeeWithdrawal.amount), 0)).filter(
            EmployeeWithdrawal.employee_id == employee_id, EmployeeWithdrawal.date >= month_start,
        ).scalar())
        if today.day <= 15:
            max_allowed = earned * D('0.5')
            if withdrawn_so_far + d_amount > max_allowed + D('0.01'):
                emp = db.query(Employee).get(employee_id)
                msg = (
                    f"تم رفض الطلب: {emp.name if emp else 'الموظف'} حصّل {earned:.2f} هذا الشهر، "
                    f"والحد المسموح بسحبه قبل يوم 15 هو 50% = {max_allowed:.2f} "
                    f"(مسحوب فعلاً {withdrawn_so_far:.2f}). يمكن سحب الباقي بعد يوم 15 من الشهر."
                )
                return RedirectResponse(f"/withdrawals?error={msg}", status_code=303)
        from services.treasury_service import TreasuryService, AccountNotSelectedError
        ts = TreasuryService(db)
        try:
            account = ts.resolve_account(account_id, "withdrawal")
        except AccountNotSelectedError as e:
            return RedirectResponse(f"/withdrawals?error={e}", status_code=303)
        withdrawal = EmployeeWithdrawal(
            employee_id=employee_id, account_id=account.id, amount=d_amount,
            withdrawal_type=withdrawal_type, date=today, notes=notes,
            status="draft", created_by=user.username,
        )
        db.add(withdrawal)
        db.commit()
        return RedirectResponse("/withdrawals", status_code=303)

    @app.post("/withdrawals/{withdrawal_id}/delete")
    def delete_withdrawal(withdrawal_id: int, db: Session = Depends(get_db),
                          user=Depends(auth.require_permission("withdrawals.manage"))):
        w = db.query(EmployeeWithdrawal).get(withdrawal_id)
        if w:
            db.delete(w)
            db.commit()
        return RedirectResponse("/withdrawals", status_code=303)

    # ??? Workflow transitions (Withdrawals) ???
    @app.post("/withdrawals/{withdrawal_id}/submit")
    def submit_withdrawal(withdrawal_id: int, db: Session = Depends(get_db),
                          user=Depends(auth.require_permission("withdrawals.manage"))):
        w = db.query(EmployeeWithdrawal).get(withdrawal_id)
        if not w: return RedirectResponse("/withdrawals", status_code=303)
        from services.workflow_service import WorkflowService
        WorkflowService(db).submit(w, user)
        db.commit()
        return RedirectResponse("/withdrawals", status_code=303)

    @app.post("/withdrawals/{withdrawal_id}/approve")
    def approve_withdrawal(withdrawal_id: int, db: Session = Depends(get_db),
                           user=Depends(auth.require_permission("withdrawals.manage"))):
        w = db.query(EmployeeWithdrawal).get(withdrawal_id)
        if not w: return RedirectResponse("/withdrawals", status_code=303)
        from services.workflow_service import WorkflowService, WorkflowError
        try:
            WorkflowService(db).review(w, user, approved=True)
        except WorkflowError as e:
            print(f"Workflow error: {e}")
        db.commit()
        return RedirectResponse("/withdrawals", status_code=303)

    @app.post("/withdrawals/{withdrawal_id}/post")
    def post_withdrawal(withdrawal_id: int, db: Session = Depends(get_db),
                        user=Depends(auth.require_permission("withdrawals.manage"))):
        w = db.query(EmployeeWithdrawal).get(withdrawal_id)
        if not w: return RedirectResponse("/withdrawals", status_code=303)
        emp = db.query(Employee).get(w.employee_id)
        from services.treasury_service import TreasuryService, InsufficientBalanceError, AccountNotSelectedError
        ts_svc = TreasuryService(db)
        try:
            account = ts_svc.resolve_account(w.account_id, "withdrawal")
            if not account:
                return RedirectResponse("/withdrawals?error=لم+يتم+اختيار+حساب+للصرف", status_code=303)
            ts_svc.validate_withdrawal(
                account.id, D(w.amount),
                f"سحب موظف: {emp.name if emp else w.employee_id} ({w.withdrawal_type})"
            )
        except (InsufficientBalanceError, AccountNotSelectedError) as e:
            return RedirectResponse(f"/withdrawals?error={e}", status_code=303)
        if not w.account_id:
            w.account_id = account.id
        from services.workflow_service import WorkflowService
        WorkflowService(db).post(w, user)
        db.add(TreasuryTransaction(
            account_id=account.id, type="out", amount=D(w.amount),
            description=f"سحب موظف: {emp.name if emp else w.employee_id} ({w.withdrawal_type})",
            date=datetime.date.today(),
            status="posted", created_by=user.username,
        ))
        ts_svc.deduct_balance(account.id, D(w.amount))
        from services.accounting_service import AccountingService
        try:
            AccountingService(db).post_withdrawal(w, created_by=user.username)
        except Exception as e:
            print(f"Accounting entry failed (non-blocking): {e}")
        db.commit()
        return RedirectResponse("/withdrawals", status_code=303)

    @app.post("/withdrawals/{withdrawal_id}/cancel")
    def cancel_withdrawal(withdrawal_id: int, db: Session = Depends(get_db),
                          user=Depends(auth.require_permission("withdrawals.manage"))):
        w = db.query(EmployeeWithdrawal).get(withdrawal_id)
        if not w: return RedirectResponse("/withdrawals", status_code=303)
        from services.workflow_service import WorkflowService
        WorkflowService(db).cancel(w, user)
        db.commit()
        return RedirectResponse("/withdrawals", status_code=303)
