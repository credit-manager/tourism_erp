"""Extended hotel management routes: contracts, room types, seasons, pricing, etc."""

from fastapi import Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import func
import datetime, json
from urllib.parse import quote
from currency_utils import D, DECIMAL_ZERO

from models import (
    Hotel, Supplier, Reservation,
    RoomType, MealPlan, HotelContract, PriceSeason,
    SeasonRoomPrice, SeasonChildPrice, SeasonExtraBedPrice,
    SeasonSingleSupplement, NationalityPricing,
    BlackoutDate, MinimumStay, CancellationPolicy, HotelTax,
)
from . import templates, get_db, paginate, pagination_ctx
import auth
from services.hotel_pricing_service import suggest_hotel_price, PricingError


def setup_hotel_enhanced_routes(app):

    # ─── Room Types ────────────────────────────────────────
    @app.post("/hotels/{hotel_id}/room-types/add")
    def add_room_type(hotel_id: int, name_ar: str = Form(...), name_en: str = Form(...),
                      max_guests: int = Form(2), description: str = Form(""),
                      db: Session = Depends(get_db),
                      user=Depends(auth.require_permission("hotels.manage"))):
        db.add(RoomType(hotel_id=hotel_id, name_ar=name_ar, name_en=name_en,
                        max_guests=max_guests, description=description))
        db.commit()
        return RedirectResponse(f"/hotels?selected={hotel_id}&tab=room_types", status_code=303)

    @app.post("/hotels/{hotel_id}/room-types/{room_type_id}/edit")
    def edit_room_type(hotel_id: int, room_type_id: int,
                       name_ar: str = Form(...), name_en: str = Form(...),
                       max_guests: int = Form(2), description: str = Form(""),
                       db: Session = Depends(get_db),
                       user=Depends(auth.require_permission("hotels.manage"))):
        rt = db.query(RoomType).filter(RoomType.id == room_type_id, RoomType.hotel_id == hotel_id).first()
        if rt:
            rt.name_ar, rt.name_en = name_ar, name_en
            rt.max_guests, rt.description = max_guests, description
            db.commit()
        return RedirectResponse(f"/hotels?selected={hotel_id}&tab=room_types", status_code=303)

    @app.post("/hotels/{hotel_id}/room-types/{room_type_id}/delete")
    def delete_room_type(hotel_id: int, room_type_id: int, db: Session = Depends(get_db),
                         user=Depends(auth.require_permission("hotels.manage"))):
        rt = db.query(RoomType).filter(RoomType.id == room_type_id, RoomType.hotel_id == hotel_id).first()
        if rt:
            db.delete(rt)
            db.commit()
        return RedirectResponse(f"/hotels?selected={hotel_id}&tab=room_types", status_code=303)

    # ─── Meal Plans ────────────────────────────────────────
    @app.post("/hotels/{hotel_id}/meal-plans/add")
    def add_meal_plan(hotel_id: int, code: str = Form(...), name_ar: str = Form(...),
                      name_en: str = Form(...), price_per_person_night: float = Form(0),
                      db: Session = Depends(get_db),
                      user=Depends(auth.require_permission("hotels.manage"))):
        db.add(MealPlan(hotel_id=hotel_id, code=code, name_ar=name_ar, name_en=name_en,
                        price_per_person_night=D(price_per_person_night)))
        db.commit()
        return RedirectResponse(f"/hotels?selected={hotel_id}&tab=meal_plans", status_code=303)

    @app.post("/hotels/{hotel_id}/meal-plans/{meal_plan_id}/edit")
    def edit_meal_plan(hotel_id: int, meal_plan_id: int,
                       code: str = Form(...), name_ar: str = Form(...),
                       name_en: str = Form(...), price_per_person_night: float = Form(0),
                       db: Session = Depends(get_db),
                       user=Depends(auth.require_permission("hotels.manage"))):
        mp = db.query(MealPlan).filter(MealPlan.id == meal_plan_id, MealPlan.hotel_id == hotel_id).first()
        if mp:
            mp.code = code
            mp.name_ar, mp.name_en = name_ar, name_en
            mp.price_per_person_night = D(price_per_person_night)
            db.commit()
        return RedirectResponse(f"/hotels?selected={hotel_id}&tab=meal_plans", status_code=303)

    @app.post("/hotels/{hotel_id}/meal-plans/{meal_plan_id}/delete")
    def delete_meal_plan(hotel_id: int, meal_plan_id: int, db: Session = Depends(get_db),
                         user=Depends(auth.require_permission("hotels.manage"))):
        mp = db.query(MealPlan).filter(MealPlan.id == meal_plan_id, MealPlan.hotel_id == hotel_id).first()
        if mp:
            db.delete(mp)
            db.commit()
        return RedirectResponse(f"/hotels?selected={hotel_id}&tab=meal_plans", status_code=303)

    # ─── Contracts ─────────────────────────────────────────
    @app.post("/hotels/{hotel_id}/contracts/add")
    def add_contract(hotel_id: int, name: str = Form(...),
                     start_date: str = Form(...), end_date: str = Form(...),
                     margin_type: str = Form("fixed"), margin_value: float = Form(0),
                     db: Session = Depends(get_db),
                     user=Depends(auth.require_permission("hotels.manage"))):
        sd = datetime.datetime.strptime(start_date, "%Y-%m-%d").date() if start_date else None
        ed = datetime.datetime.strptime(end_date, "%Y-%m-%d").date() if end_date else None
        db.add(HotelContract(hotel_id=hotel_id, name=name, start_date=sd, end_date=ed,
                             margin_type=margin_type, margin_value=D(margin_value)))
        db.commit()
        return RedirectResponse(f"/hotels?selected={hotel_id}&tab=contracts", status_code=303)

    @app.post("/hotels/{hotel_id}/contracts/{contract_id}/edit")
    def edit_contract(hotel_id: int, contract_id: int,
                      name: str = Form(...),
                      start_date: str = Form(...), end_date: str = Form(...),
                      margin_type: str = Form("fixed"), margin_value: float = Form(0),
                      is_active: int = Form(0),
                      db: Session = Depends(get_db),
                      user=Depends(auth.require_permission("hotels.manage"))):
        c = db.query(HotelContract).filter(HotelContract.id == contract_id, HotelContract.hotel_id == hotel_id).first()
        if c:
            sd = datetime.datetime.strptime(start_date, "%Y-%m-%d").date() if start_date else None
            ed = datetime.datetime.strptime(end_date, "%Y-%m-%d").date() if end_date else None
            c.name = name
            c.start_date = sd
            c.end_date = ed
            c.margin_type = margin_type
            c.margin_value = D(margin_value)
            c.is_active = is_active
            db.commit()
        return RedirectResponse(f"/hotels?selected={hotel_id}&tab=contracts", status_code=303)

    @app.post("/hotels/{hotel_id}/contracts/{contract_id}/delete")
    def delete_contract(hotel_id: int, contract_id: int, db: Session = Depends(get_db),
                        user=Depends(auth.require_permission("hotels.manage"))):
        c = db.query(HotelContract).filter(HotelContract.id == contract_id, HotelContract.hotel_id == hotel_id).first()
        if c:
            db.delete(c)
            db.commit()
        return RedirectResponse(f"/hotels?selected={hotel_id}&tab=contracts", status_code=303)

    # ─── Price Seasons ─────────────────────────────────────
    @app.post("/hotels/{hotel_id}/seasons/add")
    def add_season(hotel_id: int, name_ar: str = Form(...), name_en: str = Form(...),
                   start_date: str = Form(...), end_date: str = Form(...),
                   priority: int = Form(0),
                   db: Session = Depends(get_db),
                   user=Depends(auth.require_permission("hotels.manage"))):
        sd = datetime.datetime.strptime(start_date, "%Y-%m-%d").date() if start_date else None
        ed = datetime.datetime.strptime(end_date, "%Y-%m-%d").date() if end_date else None
        db.add(PriceSeason(hotel_id=hotel_id, name_ar=name_ar, name_en=name_en,
                           start_date=sd, end_date=ed, priority=priority))
        db.commit()
        return RedirectResponse(f"/hotels?selected={hotel_id}&tab=seasons", status_code=303)

    @app.post("/hotels/{hotel_id}/seasons/{season_id}/edit")
    def edit_season(hotel_id: int, season_id: int,
                    name_ar: str = Form(...), name_en: str = Form(...),
                    start_date: str = Form(...), end_date: str = Form(...),
                    priority: int = Form(0),
                    db: Session = Depends(get_db),
                    user=Depends(auth.require_permission("hotels.manage"))):
        s = db.query(PriceSeason).filter(PriceSeason.id == season_id, PriceSeason.hotel_id == hotel_id).first()
        if s:
            sd = datetime.datetime.strptime(start_date, "%Y-%m-%d").date() if start_date else None
            ed = datetime.datetime.strptime(end_date, "%Y-%m-%d").date() if end_date else None
            s.name_ar, s.name_en = name_ar, name_en
            s.start_date, s.end_date = sd, ed
            s.priority = priority
            db.commit()
        return RedirectResponse(f"/hotels?selected={hotel_id}&tab=seasons", status_code=303)

    @app.post("/hotels/{hotel_id}/seasons/{season_id}/delete")
    def delete_season(hotel_id: int, season_id: int, db: Session = Depends(get_db),
                      user=Depends(auth.require_permission("hotels.manage"))):
        s = db.query(PriceSeason).filter(PriceSeason.id == season_id, PriceSeason.hotel_id == hotel_id).first()
        if s:
            db.delete(s)
            db.commit()
        return RedirectResponse(f"/hotels?selected={hotel_id}&tab=seasons", status_code=303)

    # ─── Season Room Prices ────────────────────────────────
    @app.post("/seasons/{season_id}/room-prices/add")
    def add_season_room_price(season_id: int, room_type_id: int = Form(...),
                              cost_per_night: float = Form(0), sale_per_night: float = Form(0),
                              db: Session = Depends(get_db),
                              user=Depends(auth.require_permission("hotels.manage"))):
        db.add(SeasonRoomPrice(season_id=season_id, room_type_id=room_type_id,
                               cost_per_night=D(cost_per_night), sale_per_night=D(sale_per_night)))
        db.commit()
        s = db.query(PriceSeason).get(season_id)
        return RedirectResponse(f"/hotels?selected={s.hotel_id}&tab=seasons" if s else "/hotels", status_code=303)

    @app.post("/hotels/{hotel_id}/season-room-prices/{price_id}/edit")
    def edit_season_room_price(hotel_id: int, price_id: int,
                               cost_per_night: float = Form(0),
                               sale_per_night: float = Form(0),
                               db: Session = Depends(get_db),
                               user=Depends(auth.require_permission("hotels.manage"))):
        rp = db.query(SeasonRoomPrice).get(price_id)
        if rp:
            rp.cost_per_night = D(cost_per_night)
            rp.sale_per_night = D(sale_per_night)
            db.commit()
        return RedirectResponse(f"/hotels?selected={hotel_id}&tab=seasons", status_code=303)

    # ─── Child Prices ──────────────────────────────────────
    @app.post("/seasons/{season_id}/child-prices/add")
    def add_child_price(season_id: int, room_type_id: int = Form(...),
                        age_from: int = Form(0), age_to: int = Form(99),
                        price_type: str = Form("percentage"), price_value: float = Form(0),
                        db: Session = Depends(get_db),
                        user=Depends(auth.require_permission("hotels.manage"))):
        db.add(SeasonChildPrice(season_id=season_id, room_type_id=room_type_id,
                                age_from=age_from, age_to=age_to,
                                price_type=price_type, price_value=D(price_value)))
        db.commit()
        s = db.query(PriceSeason).get(season_id)
        return RedirectResponse(f"/hotels?selected={s.hotel_id}&tab=seasons" if s else "/hotels", status_code=303)

    # ─── Extra Bed Prices ──────────────────────────────────
    @app.post("/seasons/{season_id}/extra-bed-prices/add")
    def add_extra_bed_price(season_id: int, room_type_id: int = Form(...),
                            cost: float = Form(0), sale: float = Form(0),
                            db: Session = Depends(get_db),
                            user=Depends(auth.require_permission("hotels.manage"))):
        db.add(SeasonExtraBedPrice(season_id=season_id, room_type_id=room_type_id,
                                   cost=D(cost), sale=D(sale)))
        db.commit()
        s = db.query(PriceSeason).get(season_id)
        return RedirectResponse(f"/hotels?selected={s.hotel_id}&tab=seasons" if s else "/hotels", status_code=303)

    # ─── Single Supplement ─────────────────────────────────
    @app.post("/seasons/{season_id}/single-supplements/add")
    def add_single_supplement(season_id: int, room_type_id: int = Form(...),
                              cost: float = Form(0), sale: float = Form(0),
                              db: Session = Depends(get_db),
                              user=Depends(auth.require_permission("hotels.manage"))):
        db.add(SeasonSingleSupplement(season_id=season_id, room_type_id=room_type_id,
                                      cost=D(cost), sale=D(sale)))
        db.commit()
        s = db.query(PriceSeason).get(season_id)
        return RedirectResponse(f"/hotels?selected={s.hotel_id}&tab=seasons" if s else "/hotels", status_code=303)

    # ─── Nationality Pricing ───────────────────────────────
    @app.post("/hotels/{hotel_id}/nationality-pricing/add")
    def add_nationality_pricing(hotel_id: int, nationality: str = Form(...),
                                season_id: int = Form(None), room_type_id: int = Form(None),
                                sale_per_night: float = Form(None), cost_per_night: float = Form(None),
                                extra_bed_sale: float = Form(None), extra_bed_cost: float = Form(None),
                                child_price_type: str = Form(None), child_price_value: float = Form(None),
                                single_supplement_sale: float = Form(None),
                                single_supplement_cost: float = Form(None),
                                db: Session = Depends(get_db),
                                user=Depends(auth.require_permission("hotels.manage"))):
        def _d(v):
            return D(v) if v is not None else None
        db.add(NationalityPricing(
            hotel_id=hotel_id, nationality=nationality,
            season_id=season_id or None, room_type_id=room_type_id or None,
            sale_per_night=_d(sale_per_night), cost_per_night=_d(cost_per_night),
            extra_bed_sale=_d(extra_bed_sale), extra_bed_cost=_d(extra_bed_cost),
            child_price_type=child_price_type or None, child_price_value=_d(child_price_value),
            single_supplement_sale=_d(single_supplement_sale),
            single_supplement_cost=_d(single_supplement_cost),
        ))
        db.commit()
        return RedirectResponse(f"/hotels?selected={hotel_id}&tab=nationality_pricing", status_code=303)

    @app.post("/hotels/{hotel_id}/nationality-pricing/{np_id}/edit")
    def edit_nationality_pricing(hotel_id: int, np_id: int,
                                 nationality: str = Form(...),
                                 sale_per_night: float = Form(None), cost_per_night: float = Form(None),
                                 extra_bed_sale: float = Form(None), extra_bed_cost: float = Form(None),
                                 child_price_type: str = Form(None), child_price_value: float = Form(None),
                                 single_supplement_sale: float = Form(None),
                                 single_supplement_cost: float = Form(None),
                                 db: Session = Depends(get_db),
                                 user=Depends(auth.require_permission("hotels.manage"))):
        np = db.query(NationalityPricing).filter(NationalityPricing.id == np_id, NationalityPricing.hotel_id == hotel_id).first()
        if np:
            def _d(v):
                return D(v) if v is not None else None
            np.nationality = nationality
            np.sale_per_night = _d(sale_per_night)
            np.cost_per_night = _d(cost_per_night)
            np.extra_bed_sale = _d(extra_bed_sale)
            np.extra_bed_cost = _d(extra_bed_cost)
            np.child_price_type = child_price_type or None
            np.child_price_value = _d(child_price_value)
            np.single_supplement_sale = _d(single_supplement_sale)
            np.single_supplement_cost = _d(single_supplement_cost)
            db.commit()
        return RedirectResponse(f"/hotels?selected={hotel_id}&tab=nationality_pricing", status_code=303)

    @app.post("/hotels/{hotel_id}/nationality-pricing/{np_id}/delete")
    def delete_nationality_pricing(hotel_id: int, np_id: int, db: Session = Depends(get_db),
                                   user=Depends(auth.require_permission("hotels.manage"))):
        np = db.query(NationalityPricing).filter(NationalityPricing.id == np_id, NationalityPricing.hotel_id == hotel_id).first()
        if np:
            db.delete(np)
            db.commit()
        return RedirectResponse(f"/hotels?selected={hotel_id}&tab=nationality_pricing", status_code=303)

    # ─── Blackout Dates ────────────────────────────────────
    @app.post("/hotels/{hotel_id}/blackout-dates/add")
    def add_blackout_date(hotel_id: int, start_date: str = Form(...),
                          end_date: str = Form(...), reason: str = Form(""),
                          db: Session = Depends(get_db),
                          user=Depends(auth.require_permission("hotels.manage"))):
        sd = datetime.datetime.strptime(start_date, "%Y-%m-%d").date() if start_date else None
        ed = datetime.datetime.strptime(end_date, "%Y-%m-%d").date() if end_date else None
        db.add(BlackoutDate(hotel_id=hotel_id, start_date=sd, end_date=ed, reason=reason))
        db.commit()
        return RedirectResponse(f"/hotels?selected={hotel_id}&tab=blackout", status_code=303)

    @app.post("/hotels/{hotel_id}/blackout-dates/{bd_id}/edit")
    def edit_blackout_date(hotel_id: int, bd_id: int,
                           start_date: str = Form(...), end_date: str = Form(...),
                           reason: str = Form(""),
                           db: Session = Depends(get_db),
                           user=Depends(auth.require_permission("hotels.manage"))):
        bd = db.query(BlackoutDate).filter(BlackoutDate.id == bd_id, BlackoutDate.hotel_id == hotel_id).first()
        if bd:
            sd = datetime.datetime.strptime(start_date, "%Y-%m-%d").date() if start_date else None
            ed = datetime.datetime.strptime(end_date, "%Y-%m-%d").date() if end_date else None
            bd.start_date, bd.end_date, bd.reason = sd, ed, reason
            db.commit()
        return RedirectResponse(f"/hotels?selected={hotel_id}&tab=blackout", status_code=303)

    @app.post("/hotels/{hotel_id}/blackout-dates/{bd_id}/delete")
    def delete_blackout_date(hotel_id: int, bd_id: int, db: Session = Depends(get_db),
                             user=Depends(auth.require_permission("hotels.manage"))):
        bd = db.query(BlackoutDate).filter(BlackoutDate.id == bd_id, BlackoutDate.hotel_id == hotel_id).first()
        if bd:
            db.delete(bd)
            db.commit()
        return RedirectResponse(f"/hotels?selected={hotel_id}&tab=blackout", status_code=303)

    # ─── Minimum Stay ──────────────────────────────────────
    @app.post("/hotels/{hotel_id}/minimum-stays/add")
    def add_minimum_stay(hotel_id: int, min_nights: int = Form(1),
                         season_id: int = Form(None),
                         start_date: str = Form(""), end_date: str = Form(""),
                         db: Session = Depends(get_db),
                         user=Depends(auth.require_permission("hotels.manage"))):
        sd = datetime.datetime.strptime(start_date, "%Y-%m-%d").date() if start_date else None
        ed = datetime.datetime.strptime(end_date, "%Y-%m-%d").date() if end_date else None
        db.add(MinimumStay(hotel_id=hotel_id, min_nights=min_nights,
                           season_id=season_id or None, start_date=sd, end_date=ed))
        db.commit()
        return RedirectResponse(f"/hotels?selected={hotel_id}&tab=minimum_stays", status_code=303)

    @app.post("/hotels/{hotel_id}/minimum-stays/{ms_id}/edit")
    def edit_minimum_stay(hotel_id: int, ms_id: int,
                          min_nights: int = Form(1),
                          start_date: str = Form(""), end_date: str = Form(""),
                          db: Session = Depends(get_db),
                          user=Depends(auth.require_permission("hotels.manage"))):
        ms = db.query(MinimumStay).filter(MinimumStay.id == ms_id, MinimumStay.hotel_id == hotel_id).first()
        if ms:
            sd = datetime.datetime.strptime(start_date, "%Y-%m-%d").date() if start_date else None
            ed = datetime.datetime.strptime(end_date, "%Y-%m-%d").date() if end_date else None
            ms.min_nights = min_nights
            ms.start_date, ms.end_date = sd, ed
            db.commit()
        return RedirectResponse(f"/hotels?selected={hotel_id}&tab=minimum_stays", status_code=303)

    @app.post("/hotels/{hotel_id}/minimum-stays/{ms_id}/delete")
    def delete_minimum_stay(hotel_id: int, ms_id: int, db: Session = Depends(get_db),
                            user=Depends(auth.require_permission("hotels.manage"))):
        ms = db.query(MinimumStay).filter(MinimumStay.id == ms_id, MinimumStay.hotel_id == hotel_id).first()
        if ms:
            db.delete(ms)
            db.commit()
        return RedirectResponse(f"/hotels?selected={hotel_id}&tab=minimum_stays", status_code=303)

    # ─── Cancellation Policies ─────────────────────────────
    @app.post("/hotels/{hotel_id}/cancellation-policies/add")
    def add_cancellation_policy(hotel_id: int, days_before_checkin: int = Form(...),
                                refund_percent: float = Form(0), fee_percent: float = Form(0),
                                db: Session = Depends(get_db),
                                user=Depends(auth.require_permission("hotels.manage"))):
        db.add(CancellationPolicy(hotel_id=hotel_id, days_before_checkin=days_before_checkin,
                                  refund_percent=D(refund_percent), fee_percent=D(fee_percent)))
        db.commit()
        return RedirectResponse(f"/hotels?selected={hotel_id}&tab=cancellation", status_code=303)

    @app.post("/hotels/{hotel_id}/cancellation-policies/{cp_id}/edit")
    def edit_cancellation_policy(hotel_id: int, cp_id: int,
                                 days_before_checkin: int = Form(...),
                                 refund_percent: float = Form(0), fee_percent: float = Form(0),
                                 db: Session = Depends(get_db),
                                 user=Depends(auth.require_permission("hotels.manage"))):
        cp = db.query(CancellationPolicy).filter(CancellationPolicy.id == cp_id, CancellationPolicy.hotel_id == hotel_id).first()
        if cp:
            cp.days_before_checkin = days_before_checkin
            cp.refund_percent = D(refund_percent)
            cp.fee_percent = D(fee_percent)
            db.commit()
        return RedirectResponse(f"/hotels?selected={hotel_id}&tab=cancellation", status_code=303)

    @app.post("/hotels/{hotel_id}/cancellation-policies/{cp_id}/delete")
    def delete_cancellation_policy(hotel_id: int, cp_id: int, db: Session = Depends(get_db),
                                   user=Depends(auth.require_permission("hotels.manage"))):
        cp = db.query(CancellationPolicy).filter(CancellationPolicy.id == cp_id, CancellationPolicy.hotel_id == hotel_id).first()
        if cp:
            db.delete(cp)
            db.commit()
        return RedirectResponse(f"/hotels?selected={hotel_id}&tab=cancellation", status_code=303)

    # ─── Taxes ─────────────────────────────────────────────
    @app.post("/hotels/{hotel_id}/taxes/add")
    def add_hotel_tax(hotel_id: int, name_ar: str = Form(...), name_en: str = Form(...),
                      tax_type: str = Form("percentage"), value: float = Form(0),
                      applies_to: str = Form("sale"),
                      db: Session = Depends(get_db),
                      user=Depends(auth.require_permission("hotels.manage"))):
        db.add(HotelTax(hotel_id=hotel_id, name_ar=name_ar, name_en=name_en,
                        tax_type=tax_type, value=D(value), applies_to=applies_to))
        db.commit()
        return RedirectResponse(f"/hotels?selected={hotel_id}&tab=taxes", status_code=303)

    @app.post("/hotels/{hotel_id}/taxes/{tax_id}/edit")
    def edit_hotel_tax(hotel_id: int, tax_id: int,
                       name_ar: str = Form(...), name_en: str = Form(...),
                       tax_type: str = Form("percentage"), value: float = Form(0),
                       applies_to: str = Form("sale"),
                       db: Session = Depends(get_db),
                       user=Depends(auth.require_permission("hotels.manage"))):
        t = db.query(HotelTax).filter(HotelTax.id == tax_id, HotelTax.hotel_id == hotel_id).first()
        if t:
            t.name_ar, t.name_en = name_ar, name_en
            t.tax_type = tax_type
            t.value = D(value)
            t.applies_to = applies_to
            db.commit()
        return RedirectResponse(f"/hotels?selected={hotel_id}&tab=taxes", status_code=303)

    @app.post("/hotels/{hotel_id}/taxes/{tax_id}/delete")
    def delete_hotel_tax(hotel_id: int, tax_id: int, db: Session = Depends(get_db),
                         user=Depends(auth.require_permission("hotels.manage"))):
        t = db.query(HotelTax).filter(HotelTax.id == tax_id, HotelTax.hotel_id == hotel_id).first()
        if t:
            db.delete(t)
            db.commit()
        return RedirectResponse(f"/hotels?selected={hotel_id}&tab=taxes", status_code=303)

    # ─── Suggest Price API (for reservation form) ──────────
    @app.post("/hotels/suggest-price")
    def suggest_price_for_reservation(
        hotel_id: int = Form(...),
        room_type_id: int = Form(None),
        checkin_date: str = Form(...),
        checkout_date: str = Form(...),
        adults: int = Form(1),
        children: int = Form(0),
        children_ages: str = Form(""),
        extra_bed: int = Form(0),
        room_count: int = Form(1),
        nationality: str = Form(""),
        db: Session = Depends(get_db),
        user=Depends(auth.require_permission("reservations.edit")),
    ):
        try:
            ci = datetime.datetime.strptime(checkin_date, "%Y-%m-%d").date() if checkin_date else None
            co = datetime.datetime.strptime(checkout_date, "%Y-%m-%d").date() if checkout_date else None
            result = suggest_hotel_price(
                db, hotel_id, room_type_id or None,
                ci, co,
                adults=adults, children=children,
                children_ages=children_ages,
                extra_bed=bool(extra_bed),
                room_count=room_count,
                nationality=nationality or None,
            )
            return {
                "ok": True,
                "stay_cost": float(result["stay_cost"]),
                "company_cost": float(result["company_cost"]),
                "taxes": float(result["taxes"]),
                "season_name_ar": result["season_name_ar"],
                "season_name_en": result["season_name_en"],
                "nights": result["nights"],
                "breakdown": {
                    "base_per_night": result["base_sale_per_night"],
                    "extra_bed": result["extra_bed_sale"],
                    "single_supplement": result["single_supplement_sale"],
                    "child": result["child_sale"],
                },
            }
        except PricingError as e:
            return {"ok": False, "error": str(e)}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ─── API: Get room types for a hotel (JSON for dynamic dropdowns) ──
    @app.get("/hotels/{hotel_id}/room-types/json")
    def hotel_room_types_json(hotel_id: int, db: Session = Depends(get_db)):
        rts = db.query(RoomType).filter(RoomType.hotel_id == hotel_id).all()
        return [{"id": r.id, "name_ar": r.name_ar, "name_en": r.name_en, "max_guests": r.max_guests} for r in rts]

    @app.get("/hotels/{hotel_id}/meal-plans/json")
    def hotel_meal_plans_json(hotel_id: int, db: Session = Depends(get_db)):
        mps = db.query(MealPlan).filter(MealPlan.hotel_id == hotel_id).all()
        return [{"id": m.id, "code": m.code, "name_ar": m.name_ar, "name_en": m.name_en} for m in mps]
