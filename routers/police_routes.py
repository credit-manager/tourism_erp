import datetime
from fastapi import Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from models import PoliceNotification, Hotel
from . import templates, get_db
import auth


def setup_police_routes(app):
    @app.get("/police-notification", response_class=HTMLResponse)
    def police_page(request: Request, db: Session = Depends(get_db),
                    user=Depends(auth.require_permission("police.view"))):
        notifications = db.query(PoliceNotification).order_by(PoliceNotification.id.desc()).all()
        hotels = db.query(Hotel).all()
        return templates.TemplateResponse(request, "police_notification.html", {
            "request": request, "page_title": "إخطار الشرطة", "active": "police",
            "notifications": notifications, "hotels": hotels,
        })

    @app.post("/police-notification/add")
    def add_police_notification(group_leader: str = Form(...), nationality: str = Form(""),
                                tourists_count: int = Form(1), hotel_id: int = Form(None),
                                arrival_date: str = Form(None), notification_date: str = Form(None),
                                notes: str = Form(""), db: Session = Depends(get_db),
                                user=Depends(auth.require_permission("police.manage"))):
        def parse_date(s):
            try: return datetime.datetime.strptime(s, "%Y-%m-%d").date()
            except Exception: return None
        db.add(PoliceNotification(created_date=datetime.date.today(), group_leader=group_leader,
                                  nationality=nationality, tourists_count=tourists_count,
                                  hotel_id=hotel_id or None, arrival_date=parse_date(arrival_date),
                                  notification_date=parse_date(notification_date), status="pending", notes=notes))
        db.commit()
        return RedirectResponse("/police-notification", status_code=303)

    @app.post("/police-notification/{notification_id}/edit")
    def edit_police_notification(notification_id: int, group_leader: str = Form(...),
                                 nationality: str = Form(""), tourists_count: int = Form(1),
                                 hotel_id: int = Form(None), arrival_date: str = Form(None),
                                 notification_date: str = Form(None), status: str = Form("pending"),
                                 notes: str = Form(""), db: Session = Depends(get_db),
                                 user=Depends(auth.require_permission("police.manage"))):
        def parse_date(s):
            try: return datetime.datetime.strptime(s, "%Y-%m-%d").date()
            except Exception: return None
        n = db.query(PoliceNotification).get(notification_id)
        if n:
            n.group_leader, n.nationality, n.tourists_count = group_leader, nationality, tourists_count
            n.hotel_id = hotel_id or None
            n.arrival_date, n.notification_date = parse_date(arrival_date), parse_date(notification_date)
            n.status, n.notes = status, notes
            db.commit()
        return RedirectResponse("/police-notification", status_code=303)

    @app.post("/police-notification/{notification_id}/delete")
    def delete_police_notification(notification_id: int, db: Session = Depends(get_db),
                                   user=Depends(auth.require_permission("police.manage"))):
        n = db.query(PoliceNotification).get(notification_id)
        if n:
            db.delete(n)
            db.commit()
        return RedirectResponse("/police-notification", status_code=303)
