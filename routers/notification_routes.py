from fastapi import Request, Depends, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from routers import templates, get_db
import auth
from services.notification_service import NotificationService


def setup_notification_routes(app):
    @app.get("/notifications", response_class=HTMLResponse)
    def notifications_page(request: Request, db: Session = Depends(get_db)):
        user = auth.require_login(request, db)
        svc = NotificationService(db)
        notifications = svc.list_for_user(user.id, limit=100)
        svc.mark_all_read(user.id)
        db.commit()
        return templates.TemplateResponse(request, "notifications.html", {
            "request": request, "page_title": "الإشعارات - Notifications", "active": "notifications",
            "notifications": notifications,
        })

    @app.get("/notifications/dropdown", response_class=HTMLResponse)
    def notifications_dropdown(request: Request, db: Session = Depends(get_db)):
        user = auth.require_login(request, db)
        svc = NotificationService(db)
        notifications = svc.list_for_user(user.id, limit=8)
        unread = svc.unread_count(user.id)
        return templates.TemplateResponse(request, "_notifications_dropdown.html", {
            "request": request, "notifications": notifications, "unread_count": unread,
        })

    @app.post("/notifications/{notification_id}/read")
    def mark_notification_read(notification_id: int, request: Request, db: Session = Depends(get_db)):
        user = auth.require_login(request, db)
        svc = NotificationService(db)
        n = svc.mark_read(notification_id, user.id)
        db.commit()
        if n and n.link:
            return RedirectResponse(n.link, status_code=303)
        return RedirectResponse("/notifications", status_code=303)

    @app.post("/notifications/mark-all-read")
    def mark_all_notifications_read(request: Request, db: Session = Depends(get_db)):
        user = auth.require_login(request, db)
        NotificationService(db).mark_all_read(user.id)
        db.commit()
        return RedirectResponse("/notifications", status_code=303)
