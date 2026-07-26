from fastapi import Request, Form, Depends, Query
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import func
from currency_utils import D, DECIMAL_ZERO
import datetime

from models import Customer, Reservation, Employee, Collection, CustomerContact, CustomerQuote, CustomerTask, CustomerComplaint, CustomerTimeline, ReservationDocument
from . import templates, get_db, paginate, pagination_ctx
import auth

CLASSIFICATIONS = ["vip", "gold", "silver", "regular"]
SOURCES = ["direct", "facebook", "referral", "advertisement", "walk_in", "other"]
RISK_LEVELS = ["low", "medium", "high"]
CONTACT_METHODS = ["phone", "email", "whatsapp"]
TASK_STATUSES = ["pending", "in_progress", "completed", "cancelled"]
COMPLAINT_STATUSES = ["open", "in_progress", "resolved", "closed"]
QUOTE_STATUSES = ["draft", "sent", "accepted", "rejected"]


def _log_timeline(db, customer_id, type, content, reference_type=None, reference_id=None, created_by=None):
    db.add(CustomerTimeline(customer_id=customer_id, type=type, content=content,
                            reference_type=reference_type, reference_id=reference_id, created_by=created_by))
    db.commit()


def setup_customer_routes(app):
    @app.get("/customers", response_class=HTMLResponse)
    def customers_page(request: Request, db: Session = Depends(get_db), page: int = 1,
                       classification: str = "", source: str = "", type: str = "", q: str = ""):
        qry = db.query(Customer)
        if classification:
            qry = qry.filter(Customer.classification == classification)
        if source:
            qry = qry.filter(Customer.source == source)
        if type:
            qry = qry.filter(Customer.type == type)
        if q:
            qry = qry.filter(Customer.name.ilike(f"%{q}%") | Customer.phone.ilike(f"%{q}%") | Customer.email.ilike(f"%{q}%"))
        all_customers = qry.all()
        b2b_count = sum(1 for c in all_customers if c.type == "B2B")
        b2c_count = sum(1 for c in all_customers if c.type == "B2C")
        total_balance = sum(D(c.balance) for c in all_customers)
        customers, pg, tp, tt = paginate(qry.order_by(Customer.id.desc()), page)
        employees = db.query(Employee).order_by(Employee.name).all()
        return templates.TemplateResponse(request, "customers.html", {
            "request": request, "customers": customers, "page_title": "العملاء", "active": "customers",
            "b2b_count": b2b_count, "b2c_count": b2c_count, "total_balance": total_balance,
            "p": pagination_ctx(pg, tp, tt), "base_url": f"/customers?page={pg}",
            "classifications": CLASSIFICATIONS, "sources": SOURCES,
            "employees": employees,
            "f_classification": classification, "f_source": source, "f_type": type, "f_q": q,
        })

    @app.get("/customers/{customer_id}", response_class=HTMLResponse)
    def customer_profile_page(customer_id: int, request: Request, db: Session = Depends(get_db),
                              tab: str = "basic"):
        customer = db.query(Customer).get(customer_id)
        if not customer:
            return RedirectResponse("/customers", status_code=303)
        matched = db.query(Reservation).filter(Reservation.customer_id == customer_id).order_by(Reservation.id.desc()).all()
        if not matched and customer.phone:
            matched = db.query(Reservation).filter(Reservation.phone == customer.phone, Reservation.customer_id == None).order_by(Reservation.id.desc()).all()
        if not matched:
            matched = db.query(Reservation).filter(Reservation.guest_name == customer.name, Reservation.customer_id == None).order_by(Reservation.id.desc()).all()
        today = datetime.date.today()
        total_spent = sum(D(r.paid_to_office) for r in matched)
        total_trips = len(matched)
        upcoming_trips = [r for r in matched if r.checkin_date and r.checkin_date >= today]
        past_trips = [r for r in matched if not (r.checkin_date and r.checkin_date >= today)]

        contacts = db.query(CustomerContact).filter(CustomerContact.customer_id == customer_id).order_by(CustomerContact.id.desc()).all()
        quotes = db.query(CustomerQuote).filter(CustomerQuote.customer_id == customer_id).order_by(CustomerQuote.id.desc()).all()
        tasks = db.query(CustomerTask).filter(CustomerTask.customer_id == customer_id).order_by(CustomerTask.id.desc()).all()
        complaints = db.query(CustomerComplaint).filter(CustomerComplaint.customer_id == customer_id).order_by(CustomerComplaint.id.desc()).all()
        timeline = db.query(CustomerTimeline).filter(CustomerTimeline.customer_id == customer_id).order_by(CustomerTimeline.id.desc()).limit(50).all()
        collections = db.query(Collection).filter(Collection.customer_id == customer_id).order_by(Collection.id.desc()).all()
        res_ids = [r.id for r in matched]
        docs = db.query(ReservationDocument).filter(ReservationDocument.reservation_id.in_(res_ids)).order_by(ReservationDocument.id.desc()).all() if res_ids else []
        employees = db.query(Employee).order_by(Employee.name).all()

        return templates.TemplateResponse(request, "customer_profile.html", {
            "request": request, "page_title": f"ملف العميل - {customer.name}", "active": "customers",
            "customer": customer, "matched": matched, "total_spent": total_spent, "total_trips": total_trips,
            "upcoming_trips": upcoming_trips, "past_trips": past_trips,
            "contacts": contacts, "quotes": quotes, "tasks": tasks, "complaints": complaints,
            "timeline": timeline, "collections": collections, "docs": docs,
            "classifications": CLASSIFICATIONS, "sources": SOURCES, "risk_levels": RISK_LEVELS,
            "contact_methods": CONTACT_METHODS, "employees": employees,
            "task_statuses": TASK_STATUSES, "complaint_statuses": COMPLAINT_STATUSES,
            "quote_statuses": QUOTE_STATUSES, "current_tab": tab,
        })

    @app.post("/customers/{customer_id}/notes")
    def update_customer_notes(customer_id: int, notes: str = Form(""), db: Session = Depends(get_db),
                               user=Depends(auth.require_permission("customers.manage"))):
        customer = db.query(Customer).get(customer_id)
        if customer:
            customer.notes = notes
            db.commit()
        return RedirectResponse(f"/customers/{customer_id}", status_code=303)

    @app.post("/customers/add")
    def add_customer(name: str = Form(...), type: str = Form(...), phone: str = Form(""),
                     email: str = Form(""), address: str = Form(""), city: str = Form(""),
                     country: str = Form(""), nationality: str = Form(""), gender: str = Form(""),
                     date_of_birth: str = Form(""), id_number: str = Form(""), passport_no: str = Form(""),
                     classification: str = Form("regular"), source: str = Form("direct"),
                     account_manager_id: int = Form(0), credit_limit: str = Form("0"),
                     risk_level: str = Form("low"), preferred_contact_method: str = Form("phone"),
                     payment_terms: str = Form("due_on_receipt"),
                     db: Session = Depends(get_db), user=Depends(auth.require_permission("customers.manage"))):
        dob = None
        if date_of_birth:
            try:
                dob = datetime.date.fromisoformat(date_of_birth)
            except ValueError:
                pass
        am_id = account_manager_id if account_manager_id > 0 else None
        c = Customer(name=name, type=type, phone=phone, email=email, address=address,
                     city=city, country=country, nationality=nationality, gender=gender,
                     date_of_birth=dob, id_number=id_number, passport_no=passport_no,
                     classification=classification, source=source, account_manager_id=am_id,
                     credit_limit=D(credit_limit or "0"), risk_level=risk_level,
                     preferred_contact_method=preferred_contact_method,
                     payment_terms=payment_terms)
        db.add(c)
        db.commit()
        db.refresh(c)
        _log_timeline(db, c.id, "system", f"تم إنشاء العميل بواسطة {user.name if hasattr(user, 'name') else ''}", created_by=user.name if hasattr(user, 'name') else None)
        return RedirectResponse("/customers", status_code=303)

    @app.post("/customers/quick-add")
    async def quick_add_customer(request: Request, db: Session = Depends(get_db),
                                  user=Depends(auth.require_permission("reservations.add"))):
        form = await request.form()
        name = (form.get("name") or "").strip()
        phone = (form.get("phone") or "").strip()
        ctype = (form.get("type") or "B2B").strip()
        if not name:
            return JSONResponse({"ok": False, "error": "اسم العميل مطلوب."}, status_code=400)
        try:
            existing = db.query(Customer).filter(func.lower(Customer.name) == name.lower()).first()
            if existing:
                return {"ok": True, "id": existing.id, "name": existing.name, "phone": existing.phone or "", "existing": True}
            c = Customer(name=name, phone=phone, type=ctype)
            db.add(c)
            db.commit()
            db.refresh(c)
            return {"ok": True, "id": c.id, "name": c.name, "phone": c.phone or "", "existing": False}
        except Exception as e:
            db.rollback()
            return JSONResponse({"ok": False, "error": f"حصل خطأ: {str(e)}"}, status_code=500)

    @app.post("/customers/{customer_id}/edit")
    def edit_customer(customer_id: int, name: str = Form(...), type: str = Form(...), phone: str = Form(""),
                      email: str = Form(""), address: str = Form(""), city: str = Form(""),
                      country: str = Form(""), nationality: str = Form(""), gender: str = Form(""),
                      date_of_birth: str = Form(""), id_number: str = Form(""), passport_no: str = Form(""),
                      classification: str = Form("regular"), source: str = Form("direct"),
                      account_manager_id: int = Form(0), credit_limit: str = Form("0"),
                      risk_level: str = Form("low"), preferred_contact_method: str = Form("phone"),
                      payment_terms: str = Form("due_on_receipt"),
                      db: Session = Depends(get_db), user=Depends(auth.require_permission("customers.manage"))):
        c = db.query(Customer).get(customer_id)
        if c:
            dob = None
            if date_of_birth:
                try:
                    dob = datetime.date.fromisoformat(date_of_birth)
                except ValueError:
                    pass
            c.name = name; c.type = type; c.phone = phone; c.email = email
            c.address = address; c.city = city; c.country = country; c.nationality = nationality
            c.gender = gender; c.date_of_birth = dob; c.id_number = id_number; c.passport_no = passport_no
            c.classification = classification; c.source = source
            c.account_manager_id = account_manager_id if account_manager_id > 0 else None
            c.credit_limit = D(credit_limit or "0"); c.risk_level = risk_level
            c.preferred_contact_method = preferred_contact_method
            c.payment_terms = payment_terms
            db.commit()
        return RedirectResponse(f"/customers/{customer_id}?tab=basic", status_code=303)

    @app.post("/customers/{customer_id}/delete")
    def delete_customer(customer_id: int, db: Session = Depends(get_db),
                        user=Depends(auth.require_permission("customers.manage"))):
        c = db.query(Customer).get(customer_id)
        if c:
            db.delete(c)
            db.commit()
        return RedirectResponse("/customers", status_code=303)

    # ---------- Contacts CRUD ----------
    @app.post("/customers/{customer_id}/contacts/add")
    def add_contact(customer_id: int, name: str = Form(...), phone: str = Form(""),
                    email: str = Form(""), job_title: str = Form(""), is_primary: int = Form(0),
                    notes: str = Form(""), db: Session = Depends(get_db),
                    user=Depends(auth.require_permission("customers.manage"))):
        if is_primary:
            db.query(CustomerContact).filter(CustomerContact.customer_id == customer_id, CustomerContact.is_primary == 1).update({"is_primary": 0})
        db.add(CustomerContact(customer_id=customer_id, name=name, phone=phone, email=email,
                               job_title=job_title, is_primary=is_primary, notes=notes))
        db.commit()
        return RedirectResponse(f"/customers/{customer_id}?tab=contacts", status_code=303)

    @app.post("/customers/contacts/{contact_id}/edit")
    def edit_contact(contact_id: int, name: str = Form(...), phone: str = Form(""),
                     email: str = Form(""), job_title: str = Form(""), is_primary: int = Form(0),
                     notes: str = Form(""), db: Session = Depends(get_db),
                     user=Depends(auth.require_permission("customers.manage"))):
        c = db.query(CustomerContact).get(contact_id)
        if c:
            if is_primary:
                db.query(CustomerContact).filter(CustomerContact.customer_id == c.customer_id, CustomerContact.is_primary == 1).update({"is_primary": 0})
            c.name = name; c.phone = phone; c.email = email; c.job_title = job_title
            c.is_primary = is_primary; c.notes = notes
            db.commit()
        return RedirectResponse(f"/customers/{c.customer_id}?tab=contacts", status_code=303)

    @app.post("/customers/contacts/{contact_id}/delete")
    def delete_contact(contact_id: int, db: Session = Depends(get_db),
                       user=Depends(auth.require_permission("customers.manage"))):
        c = db.query(CustomerContact).get(contact_id)
        if c:
            cid = c.customer_id
            db.delete(c)
            db.commit()
            return RedirectResponse(f"/customers/{cid}?tab=contacts", status_code=303)
        return RedirectResponse("/customers", status_code=303)

    # ---------- Quotes CRUD ----------
    @app.post("/customers/{customer_id}/quotes/add")
    def add_quote(customer_id: int, total_amount: str = Form("0"), status: str = Form("draft"),
                  valid_until: str = Form(""), notes: str = Form(""), db: Session = Depends(get_db),
                  user=Depends(auth.require_permission("customers.manage"))):
        vu = None
        if valid_until:
            try:
                vu = datetime.date.fromisoformat(valid_until)
            except ValueError:
                pass
        q = CustomerQuote(customer_id=customer_id, total_amount=D(total_amount or "0"),
                          status=status, valid_until=vu, notes=notes,
                          created_by=user.name if hasattr(user, 'name') else None)
        db.add(q)
        db.commit()
        db.refresh(q)
        if not q.quote_number:
            q.quote_number = f"Q-{q.id:04d}"
            db.commit()
        _log_timeline(db, customer_id, "quote", f"تم إنشاء عرض سعر {q.quote_number} بقيمة {total_amount}",
                      reference_type="quote", reference_id=q.id, created_by=user.name if hasattr(user, 'name') else None)
        return RedirectResponse(f"/customers/{customer_id}?tab=quotes", status_code=303)

    @app.post("/customers/quotes/{quote_id}/edit")
    def edit_quote(quote_id: int, total_amount: str = Form("0"), status: str = Form("draft"),
                   valid_until: str = Form(""), notes: str = Form(""), db: Session = Depends(get_db),
                   user=Depends(auth.require_permission("customers.manage"))):
        q = db.query(CustomerQuote).get(quote_id)
        if q:
            vu = None
            if valid_until:
                try:
                    vu = datetime.date.fromisoformat(valid_until)
                except ValueError:
                    pass
            q.total_amount = D(total_amount or "0"); q.status = status; q.valid_until = vu; q.notes = notes
            db.commit()
            return RedirectResponse(f"/customers/{q.customer_id}?tab=quotes", status_code=303)
        return RedirectResponse("/customers", status_code=303)

    @app.post("/customers/quotes/{quote_id}/delete")
    def delete_quote(quote_id: int, db: Session = Depends(get_db),
                     user=Depends(auth.require_permission("customers.manage"))):
        q = db.query(CustomerQuote).get(quote_id)
        if q:
            cid = q.customer_id
            db.delete(q)
            db.commit()
            return RedirectResponse(f"/customers/{cid}?tab=quotes", status_code=303)
        return RedirectResponse("/customers", status_code=303)

    # ---------- Tasks CRUD ----------
    @app.post("/customers/{customer_id}/tasks/add")
    def add_task(customer_id: int, title: str = Form(...), description: str = Form(""),
                 due_date: str = Form(""), priority: str = Form("normal"),
                 assigned_to_id: int = Form(0), db: Session = Depends(get_db),
                 user=Depends(auth.require_permission("customers.manage"))):
        dd = None
        if due_date:
            try:
                dd = datetime.date.fromisoformat(due_date)
            except ValueError:
                pass
        t = CustomerTask(customer_id=customer_id, title=title, description=description,
                         due_date=dd, priority=priority,
                         assigned_to_id=assigned_to_id if assigned_to_id > 0 else None)
        db.add(t)
        db.commit()
        _log_timeline(db, customer_id, "task", f"تم إنشاء مهمة: {title}", reference_type="task", reference_id=t.id,
                      created_by=user.name if hasattr(user, 'name') else None)
        return RedirectResponse(f"/customers/{customer_id}?tab=tasks", status_code=303)

    @app.post("/customers/tasks/{task_id}/edit")
    def edit_task(task_id: int, title: str = Form(...), description: str = Form(""),
                  due_date: str = Form(""), status: str = Form("pending"), priority: str = Form("normal"),
                  assigned_to_id: int = Form(0), db: Session = Depends(get_db),
                  user=Depends(auth.require_permission("customers.manage"))):
        t = db.query(CustomerTask).get(task_id)
        if t:
            dd = None
            if due_date:
                try:
                    dd = datetime.date.fromisoformat(due_date)
                except ValueError:
                    pass
            t.title = title; t.description = description; t.due_date = dd
            t.status = status; t.priority = priority
            t.assigned_to_id = assigned_to_id if assigned_to_id > 0 else None
            if status == "completed" and not t.completed_at:
                t.completed_at = datetime.datetime.utcnow()
            elif status != "completed":
                t.completed_at = None
            db.commit()
            return RedirectResponse(f"/customers/{t.customer_id}?tab=tasks", status_code=303)
        return RedirectResponse("/customers", status_code=303)

    @app.post("/customers/tasks/{task_id}/delete")
    def delete_task(task_id: int, db: Session = Depends(get_db),
                    user=Depends(auth.require_permission("customers.manage"))):
        t = db.query(CustomerTask).get(task_id)
        if t:
            cid = t.customer_id
            db.delete(t)
            db.commit()
            return RedirectResponse(f"/customers/{cid}?tab=tasks", status_code=303)
        return RedirectResponse("/customers", status_code=303)

    # ---------- Complaints CRUD ----------
    @app.post("/customers/{customer_id}/complaints/add")
    def add_complaint(customer_id: int, subject: str = Form(...), description: str = Form(""),
                      db: Session = Depends(get_db),
                      user=Depends(auth.require_permission("customers.manage"))):
        c = CustomerComplaint(customer_id=customer_id, subject=subject, description=description,
                              created_by=user.name if hasattr(user, 'name') else None)
        db.add(c)
        db.commit()
        _log_timeline(db, customer_id, "complaint", f"تم تسجيل شكوى: {subject}",
                      reference_type="complaint", reference_id=c.id,
                      created_by=user.name if hasattr(user, 'name') else None)
        return RedirectResponse(f"/customers/{customer_id}?tab=complaints", status_code=303)

    @app.post("/customers/complaints/{complaint_id}/edit")
    def edit_complaint(complaint_id: int, subject: str = Form(...), description: str = Form(""),
                       status: str = Form("open"), resolution: str = Form(""),
                       db: Session = Depends(get_db),
                       user=Depends(auth.require_permission("customers.manage"))):
        c = db.query(CustomerComplaint).get(complaint_id)
        if c:
            c.subject = subject; c.description = description; c.status = status; c.resolution = resolution
            if status in ("resolved", "closed") and not c.resolved_at:
                c.resolved_at = datetime.datetime.utcnow()
            elif status not in ("resolved", "closed"):
                c.resolved_at = None
            db.commit()
            return RedirectResponse(f"/customers/{c.customer_id}?tab=complaints", status_code=303)
        return RedirectResponse("/customers", status_code=303)

    @app.post("/customers/complaints/{complaint_id}/delete")
    def delete_complaint(complaint_id: int, db: Session = Depends(get_db),
                         user=Depends(auth.require_permission("customers.manage"))):
        c = db.query(CustomerComplaint).get(complaint_id)
        if c:
            cid = c.customer_id
            db.delete(c)
            db.commit()
            return RedirectResponse(f"/customers/{cid}?tab=complaints", status_code=303)
        return RedirectResponse("/customers", status_code=303)

    # ---------- Timeline ----------
    @app.post("/customers/{customer_id}/timeline/add")
    def add_timeline(customer_id: int, type: str = Form("note"), content: str = Form(...),
                     db: Session = Depends(get_db),
                     user=Depends(auth.require_permission("customers.manage"))):
        _log_timeline(db, customer_id, type, content,
                      created_by=user.name if hasattr(user, 'name') else None)
        return RedirectResponse(f"/customers/{customer_id}?tab=timeline", status_code=303)

    # ---------- Last Contact ----------
    @app.post("/customers/{customer_id}/last-contact")
    def update_last_contact(customer_id: int, last_contact_date: str = Form(""),
                            preferred_contact_method: str = Form(""),
                            notes: str = Form(""), db: Session = Depends(get_db),
                            user=Depends(auth.require_permission("customers.manage"))):
        c = db.query(Customer).get(customer_id)
        if c:
            if last_contact_date:
                try:
                    c.last_contact_date = datetime.date.fromisoformat(last_contact_date)
                except ValueError:
                    pass
            if preferred_contact_method:
                c.preferred_contact_method = preferred_contact_method
            if notes:
                _log_timeline(db, customer_id, "call", notes,
                              created_by=user.name if hasattr(user, 'name') else None)
            db.commit()
        return RedirectResponse(f"/customers/{customer_id}?tab=last_contact", status_code=303)
