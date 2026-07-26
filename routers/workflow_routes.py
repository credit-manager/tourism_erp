"""Workflow Task routes: dashboard, update status, inline list."""

from datetime import datetime, date
from fastapi import Request, Depends, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy import func

from models import WorkflowTask, Employee, Reservation
from . import templates, get_db
import auth


def setup_workflow_routes(app):

    # ── Dashboard ──────────────────────────────────────────
    @app.get("/workflow", response_class=HTMLResponse)
    def workflow_dashboard(request: Request, db: Session = Depends(get_db),
                           user=Depends(auth.require_permission("reservations.view"))):
        today = date.today()
        # Overdue: past due_date + not completed/cancelled
        overdue = db.query(WorkflowTask).filter(
            WorkflowTask.due_date < today,
            WorkflowTask.status.in_(["pending", "in_progress"]),
        ).order_by(WorkflowTask.due_date.asc()).all()
        # Due today
        due_today = db.query(WorkflowTask).filter(
            WorkflowTask.due_date == today,
            WorkflowTask.status.in_(["pending", "in_progress"]),
        ).order_by(WorkflowTask.priority.desc()).all()
        # This week
        from datetime import timedelta
        week_end = today + timedelta(days=7)
        due_this_week = db.query(WorkflowTask).filter(
            WorkflowTask.due_date > today,
            WorkflowTask.due_date <= week_end,
            WorkflowTask.status.in_(["pending", "in_progress"]),
        ).order_by(WorkflowTask.due_date.asc()).all()
        # Recent completed
        recent_completed = db.query(WorkflowTask).filter(
            WorkflowTask.status == "completed",
        ).order_by(WorkflowTask.completed_at.desc()).limit(20).all()

        employees = db.query(Employee).all()
        return templates.TemplateResponse(request, "workflow_dashboard.html", {
            "request": request, "page_title": "سير العمل / Workflow",
            "active": "workflow",
            "overdue": overdue, "due_today": due_today,
            "due_this_week": due_this_week, "recent_completed": recent_completed,
            "employees": employees,
            "wf_today": today,
        })

    # ── Update task status (from inline or dashboard) ──────
    @app.post("/workflow/tasks/{task_id}/status")
    def update_task_status(task_id: int, status: str = Form(...),
                           request: Request = None, db: Session = Depends(get_db),
                           user=Depends(auth.require_permission("reservations.edit"))):
        task = db.query(WorkflowTask).get(task_id)
        if not task:
            return RedirectResponse("/workflow", status_code=303)
        task.status = status
        if status == "completed":
            task.completed_at = datetime.utcnow()
        db.commit()
        referer = request.headers.get("referer", "/workflow")
        return RedirectResponse(referer, status_code=303)

    # ── Assign task ────────────────────────────────────────
    @app.post("/workflow/tasks/{task_id}/assign")
    def assign_task(task_id: int, assigned_to_id: int = Form(0),
                    db: Session = Depends(get_db),
                    user=Depends(auth.require_permission("reservations.edit"))):
        task = db.query(WorkflowTask).get(task_id)
        if not task:
            return RedirectResponse("/workflow", status_code=303)
        task.assigned_to_id = assigned_to_id if assigned_to_id else None
        db.commit()
        return RedirectResponse("/workflow", status_code=303)

    # ── Add manual task to reservation ─────────────────────
    @app.post("/reservations/{reservation_id}/tasks/add")
    def add_manual_task(reservation_id: int,
                        title: str = Form(...), description: str = Form(""),
                        assigned_to_id: int = Form(0), due_date: str = Form(""),
                        priority: str = Form("normal"),
                        db: Session = Depends(get_db),
                        user=Depends(auth.require_permission("reservations.edit"))):
        r = db.query(Reservation).get(reservation_id)
        if not r:
            return RedirectResponse("/reservations", status_code=303)
        d = None
        if due_date:
            try:
                d = datetime.strptime(due_date, "%Y-%m-%d").date()
            except ValueError:
                pass
        db.add(WorkflowTask(
            reservation_id=reservation_id,
            title=title,
            description=description,
            assigned_to_id=assigned_to_id if assigned_to_id else None,
            due_date=d,
            priority=priority,
        ))
        db.commit()
        return RedirectResponse(f"/reservations/{reservation_id}/edit", status_code=303)

    # ── Task list snippet for reservation edit page ────────
    @app.get("/reservations/{reservation_id}/tasks/html", response_class=HTMLResponse)
    def reservation_tasks_html(reservation_id: int, request: Request,
                               db: Session = Depends(get_db),
                               user=Depends(auth.require_permission("reservations.view"))):
        tasks = db.query(WorkflowTask).filter(
            WorkflowTask.reservation_id == reservation_id
        ).order_by(WorkflowTask.priority.desc(), WorkflowTask.due_date.asc()).all()
        employees = db.query(Employee).all()
        lang = "ar" if request.cookies.get("lang_pref", "en") == "ar" else "en"
        if not tasks:
            return HTMLResponse(f'<div style="color:#9ca3af;font-size:13px">{ "لا توجد مهام" if lang == "ar" else "No tasks" }</div>')

        priority_cls = {"urgent": "danger", "high": "warning", "normal": "info", "low": "neutral"}
        status_labels_ar = {"pending": "بانتظار", "in_progress": "قيد التنفيذ", "completed": "مكتمل", "cancelled": "ملغي"}
        status_labels_en = {"pending": "Pending", "in_progress": "In Progress", "completed": "Completed", "cancelled": "Cancelled"}

        html = '<div style="display:flex;flex-direction:column;gap:8px">'
        for t in tasks:
            badge = priority_cls.get(t.priority, "neutral")
            st_lbl = status_labels_ar.get(t.status, t.status) if lang == "ar" else status_labels_en.get(t.status, t.status)
            html += f'<div style="display:flex;align-items:center;gap:8px;padding:8px 12px;border-radius:10px;background:#fff;border:1px solid #e5e7eb">'
            html += f'<div style="flex:1"><strong style="font-size:13px">{t.title}</strong>'
            if t.description:
                html += f'<div style="font-size:11px;color:#6b7280">{t.description}</div>'
            html += f'<div style="font-size:10px;color:#9ca3af;margin-top:2px">'
            if t.assigned_to:
                html += f'👤 {t.assigned_to.name} '
            if t.due_date:
                html += f'📅 {t.due_date}'
            html += f'</div></div>'
            # Status select
            html += f'<form method="post" action="/workflow/tasks/{t.id}/status" style="display:inline">'
            html += f'<select name="status" onchange="this.form.submit()" style="padding:4px 8px;border-radius:8px;border:1px solid #d1d5db;font-size:12px">'
            for s in ("pending", "in_progress", "completed", "cancelled"):
                sel = " selected" if s == t.status else ""
                lbl = status_labels_ar.get(s, s) if lang == "ar" else status_labels_en.get(s, s)
                html += f'<option value="{s}"{sel}>{lbl}</option>'
            html += f'</select></form>'
            html += '</div>'
        html += '</div>'
        return HTMLResponse(html)

    # ── Overdue count for badge ────────────────────────────
    @app.get("/workflow/overdue-count")
    def overdue_count(db: Session = Depends(get_db)):
        today = date.today()
        count = db.query(func.count(WorkflowTask.id)).filter(
            WorkflowTask.due_date < today,
            WorkflowTask.status.in_(["pending", "in_progress"]),
        ).scalar()
        return {"count": count or 0}
