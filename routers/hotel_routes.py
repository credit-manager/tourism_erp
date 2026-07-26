from fastapi import Request, Form, Depends, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import func
import datetime
from urllib.parse import quote
from currency_utils import D, DECIMAL_ZERO

from models import Hotel, Supplier, Reservation, TreasuryAccount, TreasuryTransaction
from . import templates, get_db, _find_hotel_by_exact_name, paginate, pagination_ctx
import auth


def setup_hotel_routes(app):
    @app.get("/hotels", response_class=HTMLResponse)
    def hotels_page(request: Request, db: Session = Depends(get_db), page: int = 1):
        all_hotels = db.query(Hotel).all()
        suppliers = db.query(Supplier).all()
        total_bookings = db.query(Reservation).count()
        total_booking_amount = D(db.query(func.coalesce(func.sum(Reservation.company_cost), 0)).scalar())
        hotels, pg, tp, tt = paginate(db.query(Hotel).order_by(Hotel.id.desc()), page)
        return templates.TemplateResponse(request, "hotels.html", {
            "request": request, "page_title": "الفنادق (Hotels)", "active": "hotels",
            "hotels": hotels, "suppliers": suppliers,
            "total_bookings": total_bookings, "total_booking_amount": total_booking_amount,
            "p": pagination_ctx(pg, tp, tt), "base_url": f"/hotels?page={pg}",
        })

    @app.post("/hotels/quick-add")
    async def quick_add_hotel(request: Request, db: Session = Depends(get_db),
                               user=Depends(auth.require_permission("reservations.add"))):
        form = await request.form()
        name = (form.get("name") or "").strip()
        city = (form.get("city") or "").strip()
        if not name:
            return JSONResponse({"ok": False, "error": "اسم الفندق مطلوب."}, status_code=400)
        try:
            existing = db.query(Hotel).filter(func.lower(Hotel.name) == name.lower()).first()
            if existing:
                return {"ok": True, "id": existing.id, "name": existing.name, "city": existing.city or "", "existing": True}
            hotel = Hotel(name=name, city=city)
            db.add(hotel)
            db.commit()
            db.refresh(hotel)
            return {"ok": True, "id": hotel.id, "name": hotel.name, "city": hotel.city or "", "existing": False}
        except Exception as e:
            db.rollback()
            return JSONResponse({"ok": False, "error": str(e)}, status_code=500)

    @app.post("/hotels/add")
    def add_hotel(name: str = Form(...), city: str = Form(""), price_per_night: float = Form(0),
                  available_rooms: int = Form(0), supplier_id: int = Form(None),
                  db: Session = Depends(get_db), user=Depends(auth.require_permission("hotels.manage"))):
        clean_name = (name or "").strip()
        clean_city = (city or "").strip()
        if not clean_name:
            return RedirectResponse(f"/hotels?error={quote('اسم الفندق مطلوب')}", status_code=303)
        if _find_hotel_by_exact_name(db, clean_name):
            return RedirectResponse(f"/hotels?error={quote(f'الفندق {clean_name} موجود بالفعل')}", status_code=303)
        db.add(Hotel(name=clean_name, city=clean_city, price_per_night=D(price_per_night),
                     available_rooms=available_rooms, supplier_id=supplier_id or None))
        db.commit()
        return RedirectResponse("/hotels?created=1", status_code=303)

    @app.get("/hotels/check-name")
    def check_hotel_name(name: str = "", db: Session = Depends(get_db)):
        clean_name = (name or "").strip()
        if not clean_name:
            return {"ok": True, "exists": False, "id": None, "name": ""}
        hotel = _find_hotel_by_exact_name(db, clean_name)
        if hotel:
            return {"ok": True, "exists": True, "id": hotel.id, "name": hotel.name}
        return {"ok": True, "exists": False, "id": None, "name": clean_name}

    @app.post("/hotels/{hotel_id}/edit")
    def edit_hotel(hotel_id: int, name: str = Form(...), city: str = Form(""), price_per_night: float = Form(0),
                   available_rooms: int = Form(0), supplier_id: int = Form(None),
                   db: Session = Depends(get_db), user=Depends(auth.require_permission("hotels.manage"))):
        h = db.query(Hotel).get(hotel_id)
        if h:
            h.name, h.city, h.price_per_night = name, city, D(price_per_night)
            h.available_rooms, h.supplier_id = available_rooms, supplier_id or None
            db.commit()
        return RedirectResponse("/hotels", status_code=303)

    @app.post("/hotels/{hotel_id}/delete")
    def delete_hotel(hotel_id: int, db: Session = Depends(get_db),
                     user=Depends(auth.require_permission("hotels.manage"))):
        h = db.query(Hotel).get(hotel_id)
        if h:
            db.delete(h)
            db.commit()
        return RedirectResponse("/hotels", status_code=303)

    @app.get("/hotels/{hotel_id}/statement", response_class=HTMLResponse)
    def hotel_statement_page(hotel_id: int, request: Request, db: Session = Depends(get_db),
                              user=Depends(auth.require_permission("hotels.manage"))):
        hotel = db.query(Hotel).get(hotel_id)
        reservations = db.query(Reservation).filter(Reservation.hotel_id == hotel_id).order_by(Reservation.id.desc()).all()
        total_stay_cost = sum(D(r.stay_cost) for r in reservations)
        total_paid = sum(D(r.paid_to_hotel) for r in reservations)
        total_remaining = total_stay_cost - total_paid
        payments = []
        if hotel and hotel.supplier_id:
            payments = db.query(TreasuryTransaction).filter(
                TreasuryTransaction.description.like(f"%فندق {hotel.name}%")
            ).order_by(TreasuryTransaction.id.desc()).all()
        accounts = db.query(TreasuryAccount).all()
        return templates.TemplateResponse(request, "hotel_statement.html", {
            "request": request, "page_title": f"كشف حساب - {hotel.name}" if hotel else "كشف حساب الفندق",
            "active": "hotels", "hotel": hotel, "reservations": reservations,
            "total_stay_cost": total_stay_cost, "total_paid": total_paid, "total_remaining": total_remaining,
            "payments": payments, "accounts": accounts,
        })

    @app.post("/hotels/{hotel_id}/pay")
    def pay_hotel(hotel_id: int, amount: float = Form(...), account_id: int = Form(None), notes: str = Form(""),
                  db: Session = Depends(get_db), user=Depends(auth.require_permission("treasury.manage"))):
        hotel = db.query(Hotel).get(hotel_id)
        d_amount = D(amount)
        if hotel and d_amount > DECIMAL_ZERO:
            from services.treasury_service import TreasuryService, InsufficientBalanceError, AccountNotSelectedError
            svc = TreasuryService(db)
            try:
                account = svc.resolve_account(account_id, "supplier_payment")
                if not account:
                    return RedirectResponse(f"/hotels/{hotel_id}/statement?error=لم+يتم+اختيار+حساب+للدفع", status_code=303)
                svc.validate_withdrawal(account.id, d_amount, f"دفعة لفندق {hotel.name}")
            except (InsufficientBalanceError, AccountNotSelectedError) as e:
                return RedirectResponse(f"/hotels/{hotel_id}/statement?error={e}", status_code=303)
            db.add(TreasuryTransaction(
                account_id=account.id, type="out", amount=d_amount,
                description=f"دفعة لفندق {hotel.name}" + (f" - {notes}" if notes else ""),
                date=datetime.date.today()
            ))
            svc.deduct_balance(account.id, d_amount)
            open_reservations = db.query(Reservation).filter(Reservation.hotel_id == hotel_id).order_by(Reservation.id.asc()).all()
            remaining_payment = d_amount
            for r in open_reservations:
                if remaining_payment <= DECIMAL_ZERO:
                    break
                owed = D(r.stay_cost) - D(r.paid_to_hotel)
                if owed > DECIMAL_ZERO:
                    applied = min(owed, remaining_payment)
                    r.paid_to_hotel = D(r.paid_to_hotel) + applied
                    remaining_payment -= applied
            db.commit()
        return RedirectResponse(f"/hotels/{hotel_id}/statement", status_code=303)
