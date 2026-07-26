from fastapi import Request, Form, Depends, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from currency_utils import D, DECIMAL_ZERO

from models import Service
from . import templates, get_db, save_upload
import auth


def setup_service_routes(app):
    @app.get("/services", response_class=HTMLResponse)
    def services_page(request: Request, db: Session = Depends(get_db)):
        services = db.query(Service).all()
        return templates.TemplateResponse(request, "services.html", {
            "request": request, "page_title": "الخدمات (Services)", "active": "services", "services": services
        })

    @app.post("/services/add")
    def add_service(name: str = Form(...), price: float = Form(0), image: UploadFile = File(None),
                    db: Session = Depends(get_db), user=Depends(auth.require_permission("services.manage"))):
        image_path = None
        if image and image.filename:
            image_path = save_upload(image, {".jpg", ".jpeg", ".png", ".gif", ".webp"})
        db.add(Service(name=name, price=D(price), image_path=image_path))
        db.commit()
        return RedirectResponse("/services", status_code=303)

    @app.post("/services/{service_id}/edit")
    def edit_service(service_id: int, name: str = Form(...), price: float = Form(0), image: UploadFile = File(None),
                     db: Session = Depends(get_db), user=Depends(auth.require_permission("services.manage"))):
        s = db.query(Service).get(service_id)
        if s:
            s.name, s.price = name, D(price)
            if image and image.filename:
                s.image_path = save_upload(image, {".jpg", ".jpeg", ".png", ".gif", ".webp"})
            db.commit()
        return RedirectResponse("/services", status_code=303)

    @app.post("/services/{service_id}/delete")
    def delete_service(service_id: int, db: Session = Depends(get_db),
                       user=Depends(auth.require_permission("services.manage"))):
        s = db.query(Service).get(service_id)
        if s:
            db.delete(s)
            db.commit()
        return RedirectResponse("/services", status_code=303)
