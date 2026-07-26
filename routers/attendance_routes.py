import datetime
from fastapi import Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy import func
from currency_utils import D, DECIMAL_ZERO

from models import (
    Employee, Shift, Attendance, LeaveRequest, Holiday, LeaveBalance, User,
    LEAVE_TYPES, LEAVE_STATUSES,
)
from . import templates, get_db
import auth


def setup_attendance_routes(app):

    # ======================== SHIFTS (الورديات) ========================

    @app.get("/shifts", response_class=HTMLResponse)
    def shifts_page(request: Request, db: Session = Depends(get_db),
                    user=Depends(auth.require_permission("shifts.manage"))):
        shifts = db.query(Shift).order_by(Shift.start_time).all()
        return templates.TemplateResponse(request, "shifts.html", {
            "request": request, "page_title": "الورديات", "active": "shifts",
            "shifts": shifts,
        })

    @app.get("/shifts/add", response_class=HTMLResponse)
    def add_shift_page(request: Request, db: Session = Depends(get_db),
                       user=Depends(auth.require_permission("shifts.manage"))):
        return templates.TemplateResponse(request, "shift_form.html", {
            "request": request, "page_title": "إضافة وردية", "active": "shifts",
            "shift": None,
        })

    @app.post("/shifts/add")
    def add_shift(name: str = Form(...), start_time: str = Form(...), end_time: str = Form(...),
                  is_active: int = Form(1), db: Session = Depends(get_db),
                  user=Depends(auth.require_permission("shifts.manage"))):
        st = datetime.datetime.strptime(start_time, "%H:%M").time()
        et = datetime.datetime.strptime(end_time, "%H:%M").time()
        shift = Shift(name=name, start_time=st, end_time=et, is_active=is_active)
        db.add(shift)
        db.commit()
        return RedirectResponse("/shifts?saved=1", status_code=303)

    @app.get("/shifts/{shift_id}/edit", response_class=HTMLResponse)
    def edit_shift_page(shift_id: int, request: Request, db: Session = Depends(get_db),
                        user=Depends(auth.require_permission("shifts.manage"))):
        shift = db.query(Shift).get(shift_id)
        if not shift:
            return RedirectResponse("/shifts?error=not_found", status_code=303)
        return templates.TemplateResponse(request, "shift_form.html", {
            "request": request, "page_title": "تعديل وردية", "active": "shifts",
            "shift": shift,
        })

    @app.post("/shifts/{shift_id}/edit")
    def edit_shift(shift_id: int, name: str = Form(...), start_time: str = Form(...),
                   end_time: str = Form(...), is_active: int = Form(1),
                   db: Session = Depends(get_db),
                   user=Depends(auth.require_permission("shifts.manage"))):
        shift = db.query(Shift).get(shift_id)
        if not shift:
            return RedirectResponse("/shifts?error=not_found", status_code=303)
        shift.name = name
        shift.start_time = datetime.datetime.strptime(start_time, "%H:%M").time()
        shift.end_time = datetime.datetime.strptime(end_time, "%H:%M").time()
        shift.is_active = is_active
        db.commit()
        return RedirectResponse("/shifts?saved=1", status_code=303)

    @app.post("/shifts/{shift_id}/delete")
    def delete_shift(shift_id: int, db: Session = Depends(get_db),
                     user=Depends(auth.require_permission("shifts.manage"))):
        shift = db.query(Shift).get(shift_id)
        if shift:
            db.delete(shift)
            db.commit()
        return RedirectResponse("/shifts?deleted=1", status_code=303)

    # ======================== ATTENDANCE (الحضور) ========================

    @app.get("/attendance", response_class=HTMLResponse)
    def attendance_page(request: Request, month: str = None, day: str = None,
                        db: Session = Depends(get_db),
                        user=Depends(auth.require_permission("attendance.view"))):
        today = datetime.date.today()
        if not month:
            month = today.strftime("%Y-%m")
        if not day:
            day = today.strftime("%Y-%m-%d")
        try:
            selected_date = datetime.datetime.strptime(day, "%Y-%m-%d").date()
        except Exception:
            selected_date = today
        year, mon = map(int, month.split("-"))
        period_start = datetime.date(year, mon, 1)
        period_end = (datetime.date(year, mon + 1, 1) - datetime.timedelta(days=1)) if mon < 12 else datetime.date(year, 12, 31)
        employees = db.query(Employee).order_by(Employee.name).all()
        shifts = db.query(Shift).order_by(Shift.start_time).all()
        records = db.query(Attendance).filter(
            Attendance.date >= period_start, Attendance.date <= period_end
        ).all()
        day_records = {a.employee_id: a for a in records if a.date == selected_date}
        summary = []
        for emp in employees:
            emp_records = [a for a in records if a.employee_id == emp.id]
            summary.append({
                "employee": emp,
                "present": sum(1 for a in emp_records if a.status == "present"),
                "absent": sum(1 for a in emp_records if a.status == "absent"),
                "leave": sum(1 for a in emp_records if a.status == "leave"),
                "holiday": sum(1 for a in emp_records if a.status == "holiday"),
                "pending": sum(1 for a in emp_records if a.approved == 0),
            })
        total_present = sum(s["present"] for s in summary)
        total_absent = sum(s["absent"] for s in summary)
        total_leave = sum(s["leave"] for s in summary)
        today_holidays = db.query(Holiday).filter(Holiday.date == selected_date).all()
        return templates.TemplateResponse(request, "attendance.html", {
            "request": request, "page_title": "الحضور والانصراف", "active": "attendance",
            "employees": employees, "shifts": shifts, "summary": summary,
            "selected_month": month, "selected_date": selected_date,
            "day_records": day_records, "records": records,
            "total_present": total_present, "total_absent": total_absent,
            "total_leave": total_leave, "today_holidays": today_holidays,
        })

    @app.post("/attendance/mark")
    def mark_attendance(employee_id: int = Form(...), status: str = Form("present"),
                        shift_id: int = Form(0), date: str = Form(None),
                        notes: str = Form(""), db: Session = Depends(get_db),
                        user=Depends(auth.require_permission("attendance.manage"))):
        the_date = datetime.datetime.strptime(date, "%Y-%m-%d").date() if date else datetime.date.today()
        now = datetime.datetime.now()
        record = db.query(Attendance).filter(
            Attendance.employee_id == employee_id, Attendance.date == the_date
        ).first()
        sid = shift_id if shift_id > 0 else None
        if record:
            record.status = status
            record.shift_id = sid
            record.notes = notes
            if status == "present" and not record.check_in:
                record.check_in = now
            elif status in ("absent", "leave"):
                if status == "absent":
                    record.check_in = None
                    record.check_out = None
        else:
            rec = Attendance(employee_id=employee_id, date=the_date, status=status,
                             shift_id=sid, notes=notes)
            if status == "present":
                rec.check_in = now
            db.add(rec)
        db.commit()
        return RedirectResponse(f"/attendance?day={the_date}", status_code=303)

    @app.post("/attendance/checkin")
    def attendance_checkin(employee_id: int = Form(...), shift_id: int = Form(0),
                           date: str = Form(None), db: Session = Depends(get_db),
                           user=Depends(auth.require_permission("attendance.manage"))):
        the_date = datetime.datetime.strptime(date, "%Y-%m-%d").date() if date else datetime.date.today()
        now = datetime.datetime.now()
        record = db.query(Attendance).filter(
            Attendance.employee_id == employee_id, Attendance.date == the_date
        ).first()
        sid = shift_id if shift_id > 0 else None
        if not record:
            record = Attendance(employee_id=employee_id, date=the_date, shift_id=sid,
                                check_in=now, status="present")
            db.add(record)
        else:
            record.check_in = now
            record.status = "present"
            if sid:
                record.shift_id = sid
        db.commit()

        late_minutes = 0
        if record.shift_id:
            shift = db.query(Shift).get(record.shift_id)
            if shift:
                ref = datetime.datetime.combine(the_date, shift.start_time)
                delta = (now - ref).total_seconds() / 60
                if delta > 5:
                    late_minutes = int(delta)
                    record.late_minutes = late_minutes
                    db.commit()
        return RedirectResponse("/attendance", status_code=303)

    @app.post("/attendance/checkout")
    def attendance_checkout(employee_id: int = Form(...), date: str = Form(None),
                            db: Session = Depends(get_db),
                            user=Depends(auth.require_permission("attendance.manage"))):
        the_date = datetime.datetime.strptime(date, "%Y-%m-%d").date() if date else datetime.date.today()
        now = datetime.datetime.now()
        record = db.query(Attendance).filter(
            Attendance.employee_id == employee_id, Attendance.date == the_date
        ).first()
        if not record:
            record = db.query(Attendance).filter(
                Attendance.employee_id == employee_id,
                Attendance.check_in.isnot(None),
                Attendance.check_out.is_(None),
            ).order_by(Attendance.date.desc()).first()
        if record and record.check_in:
            record.check_out = now
            record.status = "present"
            work_sec = (now - record.check_in).total_seconds()
            record.work_hours = D(str(round(work_sec / 3600, 2)))
            if record.shift_id:
                shift = db.query(Shift).get(record.shift_id)
                if shift:
                    shift_sec = (datetime.datetime.combine(record.date, shift.end_time) -
                                 datetime.datetime.combine(record.date, shift.start_time)).total_seconds()
                    shift_hours = shift_sec / 3600
                    overtime = max(DECIMAL_ZERO, D(str(round(work_sec / 3600 - shift_hours, 2))))
                    record.overtime_hours = overtime
            db.commit()
            return RedirectResponse(f"/attendance?day={record.date}", status_code=303)
        return RedirectResponse("/attendance?error=no_checkin", status_code=303)

    @app.get("/attendance/log", response_class=HTMLResponse)
    def attendance_log(request: Request, employee_id: str = None, month: str = None,
                       db: Session = Depends(get_db),
                       user=Depends(auth.require_permission("attendance.view"))):
        employee_id = int(employee_id) if employee_id and str(employee_id).strip() else None
        today = datetime.date.today()
        if not month:
            month = today.strftime("%Y-%m")
        year, mon = map(int, month.split("-"))
        period_start = datetime.date(year, mon, 1)
        period_end = (datetime.date(year, mon + 1, 1) - datetime.timedelta(days=1)) if mon < 12 else datetime.date(year, 12, 31)
        q = db.query(Attendance).filter(
            Attendance.date >= period_start, Attendance.date <= period_end
        )
        if employee_id:
            q = q.filter(Attendance.employee_id == employee_id)
        records = q.order_by(Attendance.date.desc(), Attendance.employee_id).all()
        employees = db.query(Employee).order_by(Employee.name).all()
        present_count = sum(1 for a in records if a.status == "present")
        absent_count = sum(1 for a in records if a.status == "absent")
        leave_count = sum(1 for a in records if a.status == "leave")
        holiday_count = sum(1 for a in records if a.status == "holiday")
        return templates.TemplateResponse(request, "attendance_log.html", {
            "request": request, "page_title": "سجل الحضور", "active": "attendance",
            "records": records, "employees": employees, "selected_month": month,
            "selected_employee_id": employee_id,
            "present_count": present_count, "absent_count": absent_count,
            "leave_count": leave_count, "holiday_count": holiday_count,
        })

    @app.get("/attendance/approve", response_class=HTMLResponse)
    def approve_attendance_page(request: Request, month: str = None,
                                db: Session = Depends(get_db),
                                user=Depends(auth.require_permission("attendance.approve"))):
        today = datetime.date.today()
        if not month:
            month = today.strftime("%Y-%m")
        year, mon = map(int, month.split("-"))
        period_start = datetime.date(year, mon, 1)
        period_end = (datetime.date(year, mon + 1, 1) - datetime.timedelta(days=1)) if mon < 12 else datetime.date(year, 12, 31)
        pending = db.query(Attendance).filter(
            Attendance.date >= period_start, Attendance.date <= period_end,
            Attendance.approved == 0,
            Attendance.status.in_(["present", "absent", "leave"]),
        ).order_by(Attendance.date, Attendance.employee_id).all()
        employees = db.query(Employee).order_by(Employee.name).all()
        return templates.TemplateResponse(request, "attendance_approve.html", {
            "request": request, "page_title": "اعتماد الحضور", "active": "attendance",
            "pending": pending, "employees": employees, "selected_month": month,
        })

    @app.post("/attendance/approve/{att_id}")
    def approve_single_attendance(att_id: int, db: Session = Depends(get_db),
                                  user=Depends(auth.require_permission("attendance.approve"))):
        record = db.query(Attendance).get(att_id)
        if record:
            record.approved = 1
            record.approved_by = user.id
            db.commit()
        return RedirectResponse("/attendance/approve", status_code=303)

    @app.post("/attendance/approve-bulk")
    def approve_bulk_attendance(month: str = Form(...), db: Session = Depends(get_db),
                                user=Depends(auth.require_permission("attendance.approve"))):
        year, mon = map(int, month.split("-"))
        period_start = datetime.date(year, mon, 1)
        period_end = (datetime.date(year, mon + 1, 1) - datetime.timedelta(days=1)) if mon < 12 else datetime.date(year, 12, 31)
        db.query(Attendance).filter(
            Attendance.date >= period_start, Attendance.date <= period_end,
            Attendance.approved == 0,
            Attendance.status.in_(["present", "absent", "leave"]),
        ).update({"approved": 1, "approved_by": user.id}, synchronize_session=False)
        db.commit()
        return RedirectResponse("/attendance/approve", status_code=303)

    # ======================== LEAVE REQUESTS (طلبات الإجازة) ========================

    @app.get("/leave-requests", response_class=HTMLResponse)
    def leave_requests_page(request: Request, status: str = None,
                            db: Session = Depends(get_db),
                            user=Depends(auth.require_permission("leaves.manage"))):
        q = db.query(LeaveRequest).join(Employee)
        if status:
            q = q.filter(LeaveRequest.status == status)
        requests = q.order_by(LeaveRequest.created_at.desc()).all()
        employees = db.query(Employee).order_by(Employee.name).all()
        return templates.TemplateResponse(request, "leave_requests.html", {
            "request": request, "page_title": "طلبات الإجازة", "active": "leave_requests",
            "requests": requests, "employees": employees, "filter_status": status,
            "LEAVE_TYPES": LEAVE_TYPES, "LEAVE_STATUSES": LEAVE_STATUSES,
        })

    @app.get("/leave-requests/add", response_class=HTMLResponse)
    def add_leave_request_page(request: Request, db: Session = Depends(get_db),
                               user=Depends(auth.require_permission("leaves.manage"))):
        employees = db.query(Employee).order_by(Employee.name).all()
        return templates.TemplateResponse(request, "leave_request_form.html", {
            "request": request, "page_title": "طلب إجازة جديد", "active": "leave_requests",
            "employees": employees, "LEAVE_TYPES": LEAVE_TYPES,
        })

    @app.post("/leave-requests/add")
    def add_leave_request(employee_id: int = Form(...), leave_type: str = Form(...),
                          start_date: str = Form(...), end_date: str = Form(...),
                          reason: str = Form(""), db: Session = Depends(get_db),
                          user=Depends(auth.require_permission("leaves.manage"))):
        sd = datetime.datetime.strptime(start_date, "%Y-%m-%d").date()
        ed = datetime.datetime.strptime(end_date, "%Y-%m-%d").date()
        lr = LeaveRequest(employee_id=employee_id, leave_type=leave_type,
                          start_date=sd, end_date=ed, reason=reason)
        db.add(lr)
        db.flush()

        emp = db.query(Employee).get(employee_id)
        from services.notification_service import NotificationService
        NotificationService(db).notify_permission(
            "leaves.approve",
            title=f"طلب إجازة جديد: {emp.name if emp else ''}",
            body=f"{leave_type} من {sd} إلى {ed}",
            link="/leave-requests",
            category="info",
            exclude_user_id=getattr(user, "id", None),
        )

        for i in range((ed - sd).days + 1):
            d = sd + datetime.timedelta(days=i)
            existing = db.query(Attendance).filter(
                Attendance.employee_id == employee_id, Attendance.date == d
            ).first()
            if not existing:
                db.add(Attendance(employee_id=employee_id, date=d, status="leave"))
            elif existing.status not in ("leave", "absent"):
                existing.status = "leave"
        db.commit()
        return RedirectResponse("/leave-requests?saved=1", status_code=303)

    @app.post("/leave-requests/{lr_id}/approve")
    def approve_leave_request(lr_id: int, db: Session = Depends(get_db),
                              user=Depends(auth.require_permission("leaves.approve"))):
        lr = db.query(LeaveRequest).get(lr_id)
        if lr and lr.status == "pending":
            lr.status = "approved"
            lr.approved_by = user.id
            db.commit()
            from services.notification_service import NotificationService
            NotificationService(db).notify_employee_user(
                lr.employee_id, title="تم اعتماد طلب الإجازة",
                body=f"{lr.leave_type}: {lr.start_date} → {lr.end_date}",
                link="/leave-requests", category="success",
            )
            db.commit()
        return RedirectResponse("/leave-requests?updated=1", status_code=303)

    @app.post("/leave-requests/{lr_id}/reject")
    def reject_leave_request(lr_id: int, db: Session = Depends(get_db),
                             user=Depends(auth.require_permission("leaves.approve"))):
        lr = db.query(LeaveRequest).get(lr_id)
        if lr and lr.status == "pending":
            lr.status = "rejected"
            lr.approved_by = user.id
            db.commit()
            from services.notification_service import NotificationService
            NotificationService(db).notify_employee_user(
                lr.employee_id, title="تم رفض طلب الإجازة",
                body=f"{lr.leave_type}: {lr.start_date} → {lr.end_date}",
                link="/leave-requests", category="danger",
            )
            db.commit()
        return RedirectResponse("/leave-requests?updated=1", status_code=303)

    # ======================== HOLIDAYS (العطلات الرسمية) ========================

    @app.get("/holidays", response_class=HTMLResponse)
    def holidays_page(request: Request, year: int = None, db: Session = Depends(get_db),
                      user=Depends(auth.require_permission("holidays.manage"))):
        today = datetime.date.today()
        if not year:
            year = today.year
        holidays = db.query(Holiday).filter(
            func.strftime("%Y", Holiday.date) == str(year)
        ).order_by(Holiday.date).all()
        return templates.TemplateResponse(request, "holidays.html", {
            "request": request, "page_title": "العطلات الرسمية", "active": "holidays",
            "holidays": holidays, "selected_year": year,
        })

    @app.post("/holidays/add")
    def add_holiday(name: str = Form(...), date: str = Form(...),
                    is_recurring: int = Form(0), db: Session = Depends(get_db),
                    user=Depends(auth.require_permission("holidays.manage"))):
        d = datetime.datetime.strptime(date, "%Y-%m-%d").date()
        h = Holiday(name=name, date=d, is_recurring=is_recurring)
        db.add(h)
        db.commit()
        return RedirectResponse("/holidays?saved=1", status_code=303)

    @app.post("/holidays/{h_id}/delete")
    def delete_holiday(h_id: int, db: Session = Depends(get_db),
                       user=Depends(auth.require_permission("holidays.manage"))):
        h = db.query(Holiday).get(h_id)
        if h:
            db.delete(h)
            db.commit()
        return RedirectResponse("/holidays?deleted=1", status_code=303)

    @app.post("/attendance/{att_id}/delete")
    def delete_attendance(att_id: int, db: Session = Depends(get_db),
                          user=Depends(auth.require_permission("attendance.manage"))):
        record = db.query(Attendance).get(att_id)
        if record:
            db.delete(record)
            db.commit()
        return RedirectResponse("/attendance/log", status_code=303)

    @app.get("/attendance/{att_id}/edit", response_class=HTMLResponse)
    def edit_attendance_page(att_id: int, request: Request, db: Session = Depends(get_db),
                             user=Depends(auth.require_permission("attendance.manage"))):
        record = db.query(Attendance).get(att_id)
        if not record:
            return RedirectResponse("/attendance/log?error=not_found", status_code=303)
        employees = db.query(Employee).order_by(Employee.name).all()
        shifts = db.query(Shift).order_by(Shift.start_time).all()
        return templates.TemplateResponse(request, "attendance_edit.html", {
            "request": request, "page_title": "تعديل سجل حضور", "active": "attendance",
            "record": record, "employees": employees, "shifts": shifts,
        })

    @app.post("/attendance/{att_id}/edit")
    def edit_attendance(att_id: int, employee_id: int = Form(...), status: str = Form("present"),
                        shift_id: int = Form(0), date: str = Form(...),
                        check_in: str = Form(None), check_out: str = Form(None),
                        notes: str = Form(""), db: Session = Depends(get_db),
                        user=Depends(auth.require_permission("attendance.manage"))):
        record = db.query(Attendance).get(att_id)
        if not record:
            return RedirectResponse("/attendance/log?error=not_found", status_code=303)
        the_date = datetime.datetime.strptime(date, "%Y-%m-%d").date()
        record.employee_id = employee_id
        record.date = the_date
        record.status = status
        record.shift_id = shift_id if shift_id > 0 else None
        record.notes = notes
        record.check_in = datetime.datetime.strptime(check_in, "%Y-%m-%dT%H:%M") if check_in else None
        record.check_out = datetime.datetime.strptime(check_out, "%Y-%m-%dT%H:%M") if check_out else None
        if record.check_in and record.check_out:
            work_sec = (record.check_out - record.check_in).total_seconds()
            record.work_hours = D(str(round(work_sec / 3600, 2)))
        db.commit()
        return RedirectResponse("/attendance/log", status_code=303)

    # ======================== ATTENDANCE MONTHLY REPORT (تقرير حضور شهري) ========================

    @app.get("/attendance/report", response_class=HTMLResponse)
    def attendance_report_page(request: Request, month: str = None, employee_id: str = None,
                               db: Session = Depends(get_db),
                               user=Depends(auth.require_permission("attendance.view"))):
        employee_id = int(employee_id) if employee_id and str(employee_id).strip() else None
        today = datetime.date.today()
        if not month:
            month = today.strftime("%Y-%m")
        year, mon = map(int, month.split("-"))
        period_start = datetime.date(year, mon, 1)
        period_end = (datetime.date(year, mon + 1, 1) - datetime.timedelta(days=1)) if mon < 12 else datetime.date(year, 12, 31)
        employees = db.query(Employee).order_by(Employee.name).all()
        records = db.query(Attendance).filter(
            Attendance.date >= period_start, Attendance.date <= period_end
        ).all()
        report = []
        for emp in employees:
            if employee_id and emp.id != employee_id:
                continue
            emp_records = [a for a in records if a.employee_id == emp.id]
            present = sum(1 for a in emp_records if a.status == "present" and a.approved)
            absent = sum(1 for a in emp_records if a.status == "absent" and a.approved)
            leave = sum(1 for a in emp_records if a.status == "leave" and a.approved)
            holiday = sum(1 for a in emp_records if a.status == "holiday")
            total_late = sum(a.late_minutes or 0 for a in emp_records)
            total_overtime = sum(a.overtime_hours or DECIMAL_ZERO for a in emp_records)
            total_work = sum(a.work_hours or DECIMAL_ZERO for a in emp_records)
            report.append({
                "employee": emp,
                "present": present, "absent": absent, "leave": leave, "holiday": holiday,
                "late_minutes": total_late, "overtime_hours": total_overtime,
                "work_hours": total_work,
            })
        return templates.TemplateResponse(request, "attendance_report.html", {
            "request": request, "page_title": "تقرير الحضور الشهري", "active": "attendance",
            "report": report, "employees": employees, "selected_month": month,
            "selected_employee_id": employee_id,
        })

    @app.get("/attendance/report/pdf")
    def attendance_report_pdf(request: Request, month: str = None, employee_id: str = None,
                              db: Session = Depends(get_db),
                              user=Depends(auth.require_permission("attendance.view"))):
        employee_id = int(employee_id) if employee_id and str(employee_id).strip() else None
        from fpdf import FPDF
        import os
        today = datetime.date.today()
        if not month:
            month = today.strftime("%Y-%m")
        year, mon = map(int, month.split("-"))
        period_start = datetime.date(year, mon, 1)
        period_end = (datetime.date(year, mon + 1, 1) - datetime.timedelta(days=1)) if mon < 12 else datetime.date(year, 12, 31)
        emp = None
        if employee_id:
            emp = db.query(Employee).get(employee_id)
        employees = [emp] if emp else db.query(Employee).order_by(Employee.name).all()
        records = db.query(Attendance).filter(
            Attendance.date >= period_start, Attendance.date <= period_end
        ).all()

        pdf = FPDF(orientation="L", format="A4")
        pdf.set_auto_page_break(auto=True, margin=15)
        pdf.add_page()

        font_dir = r"C:\Users\MG\AppData\Local\Programs\Python\Python311\Lib\site-packages\matplotlib\mpl-data\fonts\ttf"
        font_path = os.path.join(font_dir, "DejaVuSans.ttf")
        pdf.add_font("DejaVu", "", font_path)
        pdf.add_font("DejaVu", "B", os.path.join(font_dir, "DejaVuSans-Bold.ttf"))
        pdf.set_text_shaping(True)

        month_name = f"{year}-{mon:02d}"
        pdf.set_font("DejaVu", "B", 16)
        pdf.cell(0, 10, f"Attendance Report - {month_name}", new_x="LMARGIN", new_y="NEXT", align="C")
        pdf.ln(5)

        for emp_row in employees:
            emp_records = [a for a in records if a.employee_id == emp_row.id]
            if not emp_records:
                continue

            pdf.set_font("DejaVu", "B", 11)
            pdf.cell(0, 7, f"Employee: {emp_row.name}", new_x="LMARGIN", new_y="NEXT")
            pdf.set_font("DejaVu", "", 9)

            col_w = [50, 30, 26, 26, 26, 30, 30, 30]
            headers = ["Date", "Status", "Check In", "Check Out", "Work Hrs", "Late(min)", "Overtime", "Approved"]
            pdf.set_fill_color(0, 102, 204)
            pdf.set_text_color(255, 255, 255)
            for i, h in enumerate(headers):
                pdf.cell(col_w[i], 7, h, border=1, fill=True, align="C")
            pdf.ln()

            pdf.set_text_color(0, 0, 0)
            fill = False
            total_late = 0
            total_overtime = DECIMAL_ZERO
            total_work = DECIMAL_ZERO
            present_count = 0
            for rec in emp_records:
                if fill:
                    pdf.set_fill_color(240, 240, 240)
                else:
                    pdf.set_fill_color(255, 255, 255)
                vals = [
                    rec.date.strftime("%Y-%m-%d"),
                    rec.status,
                    rec.check_in.strftime("%H:%M") if rec.check_in else "-",
                    rec.check_out.strftime("%H:%M") if rec.check_out else "-",
                    str(rec.work_hours or "-"),
                    str(rec.late_minutes or 0),
                    str(rec.overtime_hours or "-"),
                    "Yes" if rec.approved else "No",
                ]
                for i, v in enumerate(vals):
                    pdf.cell(col_w[i], 6, v, border=1, fill=True, align="C")
                pdf.ln()
                fill = not fill
                if rec.status == "present" and rec.approved:
                    present_count += 1
                total_late += rec.late_minutes or 0
                total_overtime += rec.overtime_hours or DECIMAL_ZERO
                total_work += rec.work_hours or DECIMAL_ZERO

            pdf.set_font("DejaVu", "B", 9)
            pdf.set_fill_color(230, 230, 230)
            total_row = [
                "Total", f"{present_count} days",
                "", "", str(round(total_work, 2)),
                str(total_late), str(round(float(total_overtime), 2)), ""
            ]
            for i, v in enumerate(total_row):
                pdf.cell(col_w[i], 6, v, border=1, fill=True, align="C")
            pdf.ln()
            pdf.ln(5)

        pdf_bytes = bytes(pdf.output())
        from fastapi.responses import Response
        return Response(content=pdf_bytes, media_type="application/pdf",
                        headers={"Content-Disposition": f"attachment; filename=attendance_report_{month}.pdf"})

    # ======================== LEAVE BALANCE (رصيد الإجازات) ========================

    @app.get("/leave-balance", response_class=HTMLResponse)
    def leave_balance_page(request: Request, year: int = None,
                           db: Session = Depends(get_db),
                           user=Depends(auth.require_permission("leaves.manage"))):
        today = datetime.date.today()
        if not year:
            year = today.year
        employees = db.query(Employee).order_by(Employee.name).all()
        existing = {b.employee_id: b for b in db.query(LeaveBalance).filter(
            LeaveBalance.year == year
        ).all()}
        balances_data = []
        for emp in employees:
            bal = existing.get(emp.id)
            if not bal:
                entitlement = emp.annual_leave_entitlement or 21
                approved_leave_days = db.query(func.count(Attendance.id)).filter(
                    Attendance.employee_id == emp.id,
                    Attendance.status == "leave",
                    Attendance.approved == 1,
                    func.strftime("%Y", Attendance.date) == str(year),
                ).scalar() or 0
                remaining = max(0, entitlement - approved_leave_days)
                bal = LeaveBalance(employee_id=emp.id, year=year,
                                   entitlement=entitlement,
                                   used=approved_leave_days, remaining=remaining)
                db.add(bal)
                db.flush()
            balances_data.append({
                "id": bal.id,
                "employee_name": emp.name,
                "employee_id": bal.employee_id,
                "entitlement": bal.entitlement,
                "used": bal.used,
                "remaining": bal.remaining,
            })
        db.commit()
        return templates.TemplateResponse(request, "leave_balance.html", {
            "request": request, "page_title": "رصيد الإجازات السنوية", "active": "leave_balance",
            "balances": balances_data, "selected_year": year,
        })

    @app.post("/leave-balance/recalculate")
    def recalculate_leave_balance(year: int = Form(None), db: Session = Depends(get_db),
                                  user=Depends(auth.require_permission("leaves.manage"))):
        today = datetime.date.today()
        if not year:
            year = today.year
        db.query(LeaveBalance).filter(LeaveBalance.year == year).delete()
        db.commit()
        employees = db.query(Employee).all()
        for emp in employees:
            entitlement = emp.annual_leave_entitlement or 21
            approved_leave_days = db.query(func.count(Attendance.id)).filter(
                Attendance.employee_id == emp.id,
                Attendance.status == "leave",
                Attendance.approved == 1,
                func.strftime("%Y", Attendance.date) == str(year),
            ).scalar() or 0
            remaining = max(0, entitlement - approved_leave_days)
            bal = LeaveBalance(employee_id=emp.id, year=year,
                               entitlement=entitlement,
                               used=approved_leave_days, remaining=remaining)
            db.add(bal)
        db.commit()
        return RedirectResponse(f"/leave-balance?year={year}", status_code=303)

    @app.post("/leave-balance/update/{bal_id}")
    def update_leave_balance(bal_id: int, entitlement: int = Form(...), used: int = Form(...),
                             db: Session = Depends(get_db),
                             user=Depends(auth.require_permission("leaves.manage"))):
        bal = db.query(LeaveBalance).get(bal_id)
        if bal:
            bal.entitlement = entitlement
            bal.used = used
            bal.remaining = max(0, entitlement - used)
            db.commit()
        return RedirectResponse("/leave-balance", status_code=303)
