from fastapi import Request, Form, Depends, Query
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import func
from currency_utils import D, DECIMAL_ZERO
import datetime

from models import Customer, Employee, SalesOpportunity, STAGES
from . import templates, get_db, paginate, pagination_ctx
import auth


def setup_sales_pipeline_routes(app):
    @app.get("/sales-pipeline", response_class=HTMLResponse)
    def sales_pipeline_page(request: Request, db: Session = Depends(get_db)):
        opportunities = db.query(SalesOpportunity).order_by(SalesOpportunity.created_at.desc()).all()
        today = datetime.date.today()
        overdue = db.query(SalesOpportunity).filter(
            SalesOpportunity.next_followup_date.isnot(None),
            SalesOpportunity.next_followup_date < today,
            SalesOpportunity.stage.notin_(["Won", "Lost"])
        ).count()
        upcoming = db.query(SalesOpportunity).filter(
            SalesOpportunity.next_followup_date.isnot(None),
            SalesOpportunity.next_followup_date >= today,
            SalesOpportunity.stage.notin_(["Won", "Lost"])
        ).count()
        return templates.TemplateResponse(request, "sales_pipeline.html", {
            "request": request, "opportunities": opportunities, "page_title": "فرص البيع",
            "active": "sales_pipeline", "stages": STAGES, "overdue": overdue, "upcoming": upcoming,
        })

    @app.get("/sales-pipeline/list", response_class=HTMLResponse)
    def sales_pipeline_list(request: Request, db: Session = Depends(get_db), page: int = 1,
                            stage: str = "", source: str = "", q: str = ""):
        qry = db.query(SalesOpportunity)
        if stage:
            qry = qry.filter(SalesOpportunity.stage == stage)
        if source:
            qry = qry.filter(SalesOpportunity.source == source)
        if q:
            qry = qry.join(Customer).filter(
                Customer.name.ilike(f"%{q}%") | SalesOpportunity.destination.ilike(f"%{q}%")
            )
        items, pg, tp, tt = paginate(qry.order_by(SalesOpportunity.id.desc()), page)
        return templates.TemplateResponse(request, "sales_pipeline_list.html", {
            "request": request, "opportunities": items, "page_title": "قائمة الفرص",
            "active": "sales_pipeline", "stages": STAGES,
            "sources": ["direct", "facebook", "referral", "advertisement", "walk_in", "other"],
            "f_stage": stage, "f_source": source, "f_q": q,
            "p": pagination_ctx(pg, tp, tt), "base_url": f"/sales-pipeline/list?page={pg}",
        })

    @app.get("/sales-pipeline/add", response_class=HTMLResponse)
    def add_opportunity_page(request: Request, db: Session = Depends(get_db)):
        customers = db.query(Customer).order_by(Customer.name).all()
        employees = db.query(Employee).order_by(Employee.name).all()
        return templates.TemplateResponse(request, "sales_pipeline_form.html", {
            "request": request, "page_title": "إضافة فرصة جديدة", "active": "sales_pipeline",
            "stages": STAGES, "customers": customers, "employees": employees, "edit": False,
        })

    @app.post("/sales-pipeline/add")
    def add_opportunity(customer_id: int = Form(...), stage: str = Form("Lead"),
                        source: str = Form("direct"), destination: str = Form(""),
                        budget: str = Form("0"), travel_date: str = Form(""),
                        travelers_count: int = Form(1), probability: int = Form(50),
                        expected_value: str = Form("0"), sales_rep_id: int = Form(0),
                        next_followup_date: str = Form(""), loss_reason: str = Form(""),
                        notes: str = Form(""), db: Session = Depends(get_db),
                        user=Depends(auth.require_permission("customers.manage"))):
        td = None
        if travel_date:
            try:
                td = datetime.date.fromisoformat(travel_date)
            except ValueError:
                pass
        nfd = None
        if next_followup_date:
            try:
                nfd = datetime.date.fromisoformat(next_followup_date)
            except ValueError:
                pass
        op = SalesOpportunity(
            customer_id=customer_id, stage=stage, source=source, destination=destination,
            budget=D(budget or "0"), travel_date=td, travelers_count=travelers_count,
            probability=min(max(probability, 0), 100), expected_value=D(expected_value or "0"),
            sales_rep_id=sales_rep_id if sales_rep_id > 0 else None,
            next_followup_date=nfd, loss_reason=loss_reason, notes=notes,
        )
        db.add(op)
        db.commit()
        return RedirectResponse("/sales-pipeline", status_code=303)

    @app.get("/sales-pipeline/{op_id}/edit", response_class=HTMLResponse)
    def edit_opportunity_page(op_id: int, request: Request, db: Session = Depends(get_db)):
        op = db.query(SalesOpportunity).get(op_id)
        if not op:
            return RedirectResponse("/sales-pipeline", status_code=303)
        customers = db.query(Customer).order_by(Customer.name).all()
        employees = db.query(Employee).order_by(Employee.name).all()
        return templates.TemplateResponse(request, "sales_pipeline_form.html", {
            "request": request, "page_title": "تعديل الفرصة", "active": "sales_pipeline",
            "stages": STAGES, "customers": customers, "employees": employees,
            "op": op, "edit": True,
        })

    @app.post("/sales-pipeline/{op_id}/edit")
    def edit_opportunity(op_id: int, customer_id: int = Form(...), stage: str = Form("Lead"),
                         source: str = Form("direct"), destination: str = Form(""),
                         budget: str = Form("0"), travel_date: str = Form(""),
                         travelers_count: int = Form(1), probability: int = Form(50),
                         expected_value: str = Form("0"), sales_rep_id: int = Form(0),
                         next_followup_date: str = Form(""), loss_reason: str = Form(""),
                         notes: str = Form(""), db: Session = Depends(get_db),
                         user=Depends(auth.require_permission("customers.manage"))):
        op = db.query(SalesOpportunity).get(op_id)
        if op:
            td = None
            if travel_date:
                try:
                    td = datetime.date.fromisoformat(travel_date)
                except ValueError:
                    pass
            nfd = None
            if next_followup_date:
                try:
                    nfd = datetime.date.fromisoformat(next_followup_date)
                except ValueError:
                    pass
            op.customer_id = customer_id; op.stage = stage; op.source = source
            op.destination = destination; op.budget = D(budget or "0"); op.travel_date = td
            op.travelers_count = travelers_count; op.probability = min(max(probability, 0), 100)
            op.expected_value = D(expected_value or "0")
            op.sales_rep_id = sales_rep_id if sales_rep_id > 0 else None
            op.next_followup_date = nfd; op.loss_reason = loss_reason; op.notes = notes
            db.commit()
        return RedirectResponse("/sales-pipeline", status_code=303)

    @app.post("/sales-pipeline/{op_id}/delete")
    def delete_opportunity(op_id: int, db: Session = Depends(get_db),
                           user=Depends(auth.require_permission("customers.manage"))):
        op = db.query(SalesOpportunity).get(op_id)
        if op:
            db.delete(op)
            db.commit()
        return RedirectResponse("/sales-pipeline", status_code=303)

    @app.post("/sales-pipeline/{op_id}/stage")
    def update_stage(op_id: int, stage: str = Form(...), db: Session = Depends(get_db),
                     user=Depends(auth.require_permission("customers.manage"))):
        op = db.query(SalesOpportunity).get(op_id)
        if op:
            op.stage = stage
            db.commit()
            return {"ok": True}
        return JSONResponse({"ok": False, "error": "Not found"}, status_code=404)

    @app.get("/sales-pipeline/alerts/count")
    def alerts_count(db: Session = Depends(get_db)):
        today = datetime.date.today()
        overdue = db.query(SalesOpportunity).filter(
            SalesOpportunity.next_followup_date.isnot(None),
            SalesOpportunity.next_followup_date < today,
            SalesOpportunity.stage.notin_(["Won", "Lost"])
        ).count()
        upcoming = db.query(SalesOpportunity).filter(
            SalesOpportunity.next_followup_date.isnot(None),
            SalesOpportunity.next_followup_date >= today,
            SalesOpportunity.stage.notin_(["Won", "Lost"])
        ).count()
        return {"overdue": overdue, "upcoming": upcoming}

    @app.get("/sales-pipeline/alerts")
    def sales_alerts(request: Request, db: Session = Depends(get_db)):
        today = datetime.date.today()
        overdue = db.query(SalesOpportunity).filter(
            SalesOpportunity.next_followup_date.isnot(None),
            SalesOpportunity.next_followup_date < today,
            SalesOpportunity.stage.notin_(["Won", "Lost"])
        ).all()
        upcoming = db.query(SalesOpportunity).filter(
            SalesOpportunity.next_followup_date.isnot(None),
            SalesOpportunity.next_followup_date >= today,
            SalesOpportunity.stage.notin_(["Won", "Lost"])
        ).order_by(SalesOpportunity.next_followup_date).limit(20).all()
        return templates.TemplateResponse(request, "sales_pipeline_alerts.html", {
            "request": request, "overdue": overdue, "upcoming": upcoming,
            "page_title": "التنبيهات", "active": "sales_pipeline",
        })
