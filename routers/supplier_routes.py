import datetime
from fastapi import Request, Form, Depends, Query
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import func
from currency_utils import D, DECIMAL_ZERO

from models import Supplier, SupplierInvoice, SupplierPayment
from . import templates, get_db, paginate, pagination_ctx
import auth
from services.supplier_rating_service import SupplierRatingService


def setup_supplier_routes(app):
    @app.get("/suppliers", response_class=HTMLResponse)
    def suppliers_page(request: Request, db: Session = Depends(get_db), page: int = 1):
        all_suppliers = db.query(Supplier).all()
        total_due = sum(D(s.balance) for s in all_suppliers)
        hotel_suppliers = sum(1 for s in all_suppliers if s.type == "hotel")
        suppliers, pg, tp, tt = paginate(db.query(Supplier).order_by(Supplier.id.desc()), page)
        return templates.TemplateResponse(request, "suppliers.html", {
            "request": request, "suppliers": suppliers, "page_title": "المنفذين / الفنادق", "active": "suppliers",
            "total_due": total_due, "hotel_suppliers": hotel_suppliers,
            "p": pagination_ctx(pg, tp, tt), "base_url": f"/suppliers?page={pg}",
        })

    @app.post("/suppliers/add")
    def add_supplier(name: str = Form(...), type: str = Form(...), phone: str = Form(""), db: Session = Depends(get_db),
                     user=Depends(auth.require_permission("suppliers.manage"))):
        db.add(Supplier(name=name, type=type, phone=phone))
        db.commit()
        return RedirectResponse("/suppliers", status_code=303)

    @app.post("/suppliers/{supplier_id}/edit")
    def edit_supplier(supplier_id: int, name: str = Form(...), type: str = Form(...), phone: str = Form(""),
                      db: Session = Depends(get_db), user=Depends(auth.require_permission("suppliers.manage"))):
        s = db.query(Supplier).get(supplier_id)
        if s:
            s.name, s.type, s.phone = name, type, phone
            db.commit()
        return RedirectResponse("/suppliers", status_code=303)

    @app.post("/suppliers/{supplier_id}/delete")
    def delete_supplier(supplier_id: int, db: Session = Depends(get_db),
                        user=Depends(auth.require_permission("suppliers.manage"))):
        s = db.query(Supplier).get(supplier_id)
        if s:
            db.delete(s)
            db.commit()
        return RedirectResponse("/suppliers", status_code=303)

    @app.post("/suppliers/quick-add")
    async def quick_add_supplier(request: Request, db: Session = Depends(get_db),
                                  user=Depends(auth.require_permission("reservations.add"))):
        form = await request.form()
        name = (form.get("name") or "").strip()
        stype = (form.get("type") or "hotel").strip()
        phone = (form.get("phone") or "").strip()
        if not name:
            return JSONResponse({"ok": False, "error": "اسم الشركة / المورد مطلوب."}, status_code=400)
        try:
            existing = db.query(Supplier).filter(func.lower(Supplier.name) == name.lower()).first()
            if existing:
                return {"ok": True, "id": existing.id, "name": existing.name,
                        "type": existing.type or "", "phone": existing.phone or "", "existing": True}
            sup = Supplier(name=name, type=stype, phone=phone)
            db.add(sup)
            db.commit()
            db.refresh(sup)
            return {"ok": True, "id": sup.id, "name": sup.name,
                    "type": sup.type or "", "phone": sup.phone or "", "existing": False}
        except Exception as e:
            db.rollback()
            return JSONResponse({"ok": False, "error": str(e)}, status_code=500)

    @app.get("/suppliers/ledger", response_class=HTMLResponse)
    def supplier_ledger(request: Request, db: Session = Depends(get_db),
                        supplier_id: int = Query(None),
                        user=Depends(auth.require_permission("supplier_invoices.view"))):
        try:
            suppliers = db.query(Supplier).order_by(Supplier.name).all()
            selected = None
            entries = []
            aging = {"current": D(0), "days_31_60": D(0), "days_61_90": D(0), "days_90_plus": D(0)}
            due_soon = []
            alerts = []

            if supplier_id:
                selected = db.query(Supplier).get(supplier_id)
                if selected:
                    invoices = db.query(SupplierInvoice).filter(
                        SupplierInvoice.supplier_id == supplier_id,
                        SupplierInvoice.status != "cancelled"
                    ).order_by(SupplierInvoice.invoice_date, SupplierInvoice.id).all()

                    payments = db.query(SupplierPayment).filter(
                        SupplierPayment.supplier_id == supplier_id,
                        SupplierPayment.status != "cancelled"
                    ).order_by(SupplierPayment.date, SupplierPayment.id).all()

                    for inv in invoices:
                        entries.append({
                            "date": inv.invoice_date,
                            "type": "invoice",
                            "ref": inv.invoice_number,
                            "description": f"فاتورة {inv.invoice_number}",
                            "debit": D(inv.total_amount or 0),
                            "credit": D(0),
                            "due_date": inv.due_date,
                            "status": inv.status,
                            "link": f"/suppliers/invoices/{inv.id}",
                        })

                    for pmt in payments:
                        entries.append({
                            "date": pmt.date,
                            "type": "payment",
                            "ref": pmt.payment_number,
                            "description": f"دفعة {pmt.payment_number}",
                            "debit": D(0),
                            "credit": D(pmt.total_amount or 0),
                            "due_date": None,
                            "status": pmt.status,
                            "link": f"/suppliers/payments/{pmt.id}",
                        })

                    entries.sort(key=lambda e: (e["date"] or datetime.date.min, e["type"]))

                    running = D(0)
                    for e in entries:
                        running = running + e["debit"] - e["credit"]
                        e["balance"] = running

                    for inv in invoices:
                        if inv.status in ("draft", "approved", "posted"):
                            amt = D(inv.total_amount or 0)
                            if inv.due_date:
                                days_overdue = (datetime.date.today() - inv.due_date).days
                                if days_overdue <= 0:
                                    aging["current"] += amt
                                elif days_overdue <= 30:
                                    aging["days_31_60"] += amt
                                elif days_overdue <= 60:
                                    aging["days_61_90"] += amt
                                else:
                                    aging["days_90_plus"] += amt
                            else:
                                aging["current"] += amt

                    for inv in invoices:
                        if inv.status in ("draft", "approved", "posted") and inv.due_date:
                            days = (inv.due_date - datetime.date.today()).days
                            if 0 <= days <= 7:
                                due_soon.append(inv)
                            if days < 0:
                                alerts.append({"type": "overdue", "invoice": inv, "days": abs(days)})
                            elif days <= 3:
                                alerts.append({"type": "due_soon", "invoice": inv, "days": days})

            return templates.TemplateResponse(request, "supplier_ledger.html", {
                "active": "supplier_ledger",
                "page_title": "كشف حساب الموردين",
                "suppliers": suppliers,
                "selected": selected,
                "selected_id": supplier_id,
                "entries": entries,
                "aging": aging,
                "due_soon": due_soon,
                "alerts": alerts,
            })
        except Exception as e:
            return templates.TemplateResponse(request, "supplier_ledger.html", {
                "active": "supplier_ledger",
                "page_title": "كشف حساب الموردين",
                "suppliers": [],
                "selected": None,
                "selected_id": None,
                "entries": [],
                "aging": {"current": 0, "days_31_60": 0, "days_61_90": 0, "days_90_plus": 0},
                "due_soon": [],
                "alerts": [],
                "error": str(e),
            })

    @app.get("/suppliers/rating", response_class=HTMLResponse)
    def supplier_rating(request: Request, db: Session = Depends(get_db),
                        supplier_type: str = Query(None),
                        user=Depends(auth.require_permission("supplier_invoices.view"))):
        try:
            svc = SupplierRatingService(db)
            ratings = svc.compute_all()
            suggestions = svc.get_suggestions(supplier_type=supplier_type)

            if supplier_type:
                ratings = [r for r in ratings if r["supplier_type"] == supplier_type]

            type_names = {"hotel": "فنادق", "transport": "نقل", "guide": "مرشدين", "local_company": "شركات محلية"}
            selected_type_name = type_names.get(supplier_type, "") if supplier_type else ""

            # compute averages
            avg_overall = 0
            cost_avg = 0
            speed_avg = 0
            quality_avg = 0
            if ratings:
                avg_overall = sum(r["overall"] for r in ratings) / len(ratings)
                cost_avg = sum(r["dimensions"]["cost_accuracy"]["score"] for r in ratings) / len(ratings)
                speed_avg = sum(r["dimensions"]["confirmation_speed"]["score"] for r in ratings) / len(ratings)
                quality_avg = sum(r["dimensions"]["service_quality"]["score"] for r in ratings) / len(ratings)

            return templates.TemplateResponse(request, "supplier_rating.html", {
                "active": "supplier_rating",
                "page_title": "تقييم الموردين",
                "ratings": ratings,
                "suggestions": suggestions,
                "supplier_type": supplier_type,
                "selected_type_name": selected_type_name,
                "avg_overall": int(round(avg_overall)),
                "cost_avg": int(round(cost_avg)),
                "speed_avg": int(round(speed_avg)),
                "quality_avg": int(round(quality_avg)),
                "total_suppliers": len(ratings),
            })
        except Exception as e:
            return templates.TemplateResponse(request, "supplier_rating.html", {
                "active": "supplier_rating",
                "page_title": "تقييم الموردين",
                "ratings": [],
                "suggestions": {},
                "supplier_type": supplier_type,
                "selected_type_name": "",
                "avg_overall": 0,
                "cost_avg": 0,
                "speed_avg": 0,
                "quality_avg": 0,
                "total_suppliers": 0,
                "error": str(e),
            })
