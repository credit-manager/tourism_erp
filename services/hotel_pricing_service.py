"""Hotel pricing engine: suggests stay_cost and company_cost based on contract, season, room type, nationality, etc."""

from decimal import Decimal
from datetime import date, datetime
from sqlalchemy.orm import Session
from models import (
    PriceSeason, SeasonRoomPrice, SeasonChildPrice,
    SeasonExtraBedPrice, SeasonSingleSupplement,
    NationalityPricing, BlackoutDate, MinimumStay,
    CancellationPolicy, HotelTax, HotelContract,
    RoomType, MealPlan, Hotel, DECIMAL_ZERO, D,
)


class PricingError(Exception):
    pass


def find_season(db: Session, hotel_id: int, dt: date) -> PriceSeason | None:
    """Find the active season for a hotel on a given date (highest priority wins)."""
    return db.query(PriceSeason).filter(
        PriceSeason.hotel_id == hotel_id,
        PriceSeason.start_date <= dt,
        PriceSeason.end_date >= dt,
    ).order_by(PriceSeason.priority.desc(), PriceSeason.id.desc()).first()


def check_blackout(db: Session, hotel_id: int, checkin: date, checkout: date):
    """Raise if any blackout date overlaps the stay period."""
    overlap = db.query(BlackoutDate).filter(
        BlackoutDate.hotel_id == hotel_id,
        BlackoutDate.start_date < checkout,
        BlackoutDate.end_date > checkin,
    ).first()
    if overlap:
        raise PricingError(
            f"تواريخ الحظر: {overlap.start_date} إلى {overlap.end_date}"
            f" — {overlap.reason or ''}"
        )


def check_min_stay(db: Session, hotel_id: int, season_id: int | None, nights: int):
    """Raise if nights < minimum stay requirement."""
    q = db.query(MinimumStay).filter(MinimumStay.hotel_id == hotel_id)
    if season_id:
        q = q.filter((MinimumStay.season_id == season_id) | (MinimumStay.season_id.is_(None)))
    rule = q.order_by(MinimumStay.min_nights.desc()).first()
    if rule and nights < rule.min_nights:
        raise PricingError(
            f"الحد الأدنى للإقامة {rule.min_nights} ليالٍ"
        )


def get_room_price(db: Session, season_id: int, room_type_id: int,
                   nationality: str | None = None) -> tuple[Decimal, Decimal]:
    """Return (cost_per_night, sale_per_night). Checks nationality override first."""
    # 1. Nationality override
    if nationality:
        np = db.query(NationalityPricing).filter(
            NationalityPricing.season_id == season_id,
            NationalityPricing.room_type_id == room_type_id,
            NationalityPricing.nationality == nationality,
        ).first()
        if np and np.sale_per_night is not None:
            return (np.cost_per_night or DECIMAL_ZERO, np.sale_per_night)
    # 2. Season price
    rp = db.query(SeasonRoomPrice).filter(
        SeasonRoomPrice.season_id == season_id,
        SeasonRoomPrice.room_type_id == room_type_id,
    ).first()
    if rp:
        return (rp.cost_per_night, rp.sale_per_night)
    return (DECIMAL_ZERO, DECIMAL_ZERO)


def get_single_supplement(db: Session, season_id: int, room_type_id: int,
                          nationality: str | None = None) -> tuple[Decimal, Decimal]:
    """Return (supplement_cost, supplement_sale)."""
    if nationality:
        np = db.query(NationalityPricing).filter(
            NationalityPricing.season_id == season_id,
            NationalityPricing.room_type_id == room_type_id,
            NationalityPricing.nationality == nationality,
        ).first()
        if np and np.single_supplement_sale is not None:
            return (np.single_supplement_cost or DECIMAL_ZERO, np.single_supplement_sale)
    ss = db.query(SeasonSingleSupplement).filter(
        SeasonSingleSupplement.season_id == season_id,
        SeasonSingleSupplement.room_type_id == room_type_id,
    ).first()
    if ss:
        return (ss.cost, ss.sale)
    return (DECIMAL_ZERO, DECIMAL_ZERO)


def get_extra_bed_price(db: Session, season_id: int, room_type_id: int,
                        nationality: str | None = None) -> tuple[Decimal, Decimal]:
    """Return (extra_bed_cost, extra_bed_sale)."""
    if nationality:
        np = db.query(NationalityPricing).filter(
            NationalityPricing.season_id == season_id,
            NationalityPricing.room_type_id == room_type_id,
            NationalityPricing.nationality == nationality,
        ).first()
        if np and np.extra_bed_sale is not None:
            return (np.extra_bed_cost or DECIMAL_ZERO, np.extra_bed_sale)
    eb = db.query(SeasonExtraBedPrice).filter(
        SeasonExtraBedPrice.season_id == season_id,
        SeasonExtraBedPrice.room_type_id == room_type_id,
    ).first()
    if eb:
        return (eb.cost, eb.sale)
    return (DECIMAL_ZERO, DECIMAL_ZERO)


def get_child_price(db: Session, season_id: int, room_type_id: int, age: int,
                    nationality: str | None = None, base_sale: Decimal = DECIMAL_ZERO) -> Decimal:
    """Return the sale price for one child per night based on age."""
    if nationality:
        np = db.query(NationalityPricing).filter(
            NationalityPricing.season_id == season_id,
            NationalityPricing.room_type_id == room_type_id,
            NationalityPricing.nationality == nationality,
            NationalityPricing.child_price_type.isnot(None),
        ).first()
        if np:
            return _calc_child_price(np.child_price_type, np.child_price_value, age, base_sale)
    cp = db.query(SeasonChildPrice).filter(
        SeasonChildPrice.season_id == season_id,
        SeasonChildPrice.room_type_id == room_type_id,
        SeasonChildPrice.age_from <= age,
        SeasonChildPrice.age_to >= age,
    ).first()
    if cp:
        return _calc_child_price(
            cp.price_type, cp.price_value, age, base_sale,
        )
    return DECIMAL_ZERO


def _calc_child_price(price_type: str, value: Decimal, age: int, base_sale: Decimal) -> Decimal:
    if price_type == "free":
        return DECIMAL_ZERO
    elif price_type == "percentage":
        return (base_sale * value) / D(100)
    elif price_type == "fixed":
        return value
    return DECIMAL_ZERO


def get_taxes(db: Session, hotel_id: int, sale_amount: Decimal, cost_amount: Decimal) -> tuple[Decimal, Decimal]:
    """Return (total_tax_on_sale, total_tax_on_cost)."""
    taxes = db.query(HotelTax).filter(HotelTax.hotel_id == hotel_id).all()
    sale_tax = DECIMAL_ZERO
    cost_tax = DECIMAL_ZERO
    for t in taxes:
        val = (sale_amount * t.value / D(100)) if t.tax_type == "percentage" else t.value
        if t.applies_to in ("sale", "both"):
            sale_tax += val
        if t.applies_to in ("cost", "both"):
            cost_tax += val
    return (sale_tax, cost_tax)


def get_active_contract(db: Session, hotel_id: int, dt: date) -> HotelContract | None:
    return db.query(HotelContract).filter(
        HotelContract.hotel_id == hotel_id,
        HotelContract.start_date <= dt,
        HotelContract.end_date >= dt,
        HotelContract.is_active == 1,
    ).order_by(HotelContract.id.desc()).first()


def calc_company_cost(stay_cost: Decimal, contract: HotelContract | None,
                      taxes_sale: Decimal) -> Decimal:
    """Calculate sale price from cost using contract margin."""
    if not contract:
        return stay_cost + taxes_sale
    if contract.margin_type == "percentage":
        return stay_cost + (stay_cost * contract.margin_value / D(100)) + taxes_sale
    else:
        return stay_cost + contract.margin_value + taxes_sale


def suggest_hotel_price(
    db: Session,
    hotel_id: int,
    room_type_id: int | None,
    checkin_date: date,
    checkout_date: date,
    adults: int = 1,
    children: int = 0,
    children_ages: str = "",
    extra_bed: bool = False,
    room_count: int = 1,
    nationality: str | None = None,
) -> dict:
    """Compute suggested pricing for a reservation stay."""
    if not hotel_id or not checkin_date or not checkout_date:
        raise PricingError("يجب اختيار الفندق وتاريخ الوصول والمغادرة")
    if checkout_date <= checkin_date:
        raise PricingError("تاريخ المغادرة يجب أن يكون بعد تاريخ الوصول")

    nights = (checkout_date - checkin_date).days

    # Blackout check
    check_blackout(db, hotel_id, checkin_date, checkout_date)

    # Season
    season = find_season(db, hotel_id, checkin_date)
    season_id = season.id if season else None

    # Min stay
    check_min_stay(db, hotel_id, season_id, nights)

    # Room price
    cost_per_night = DECIMAL_ZERO
    sale_per_night = DECIMAL_ZERO
    if room_type_id:
        cost_per_night, sale_per_night = get_room_price(db, season_id, room_type_id, nationality)

    # Base stay cost
    base_cost = cost_per_night * room_count * nights
    base_sale = sale_per_night * room_count * nights

    # Single supplement
    supp_cost = DECIMAL_ZERO
    supp_sale = DECIMAL_ZERO
    if adults == 1 and room_count == 1 and room_type_id:
        supp_cost, supp_sale = get_single_supplement(db, season_id, room_type_id, nationality)
        supp_cost *= nights
        supp_sale *= nights

    # Children
    child_cost_total = DECIMAL_ZERO
    child_sale_total = DECIMAL_ZERO
    if children > 0 and children_ages and room_type_id:
        ages = []
        for part in children_ages.replace("،", ",").split(","):
            part = part.strip()
            if part:
                try:
                    ages.append(int(part))
                except ValueError:
                    pass
        for age in ages:
            cp = get_child_price(db, season_id, room_type_id, age, nationality, sale_per_night)
            child_sale_total += cp * nights
            # Child cost = same logic but from cost base
            child_cost_total += cp * nights  # simplified: cost = sale same

    # Extra bed
    eb_cost = DECIMAL_ZERO
    eb_sale = DECIMAL_ZERO
    if extra_bed and room_type_id:
        eb_cost, eb_sale = get_extra_bed_price(db, season_id, room_type_id, nationality)
        eb_cost *= nights
        eb_sale *= nights

    # Totals
    total_stay_cost = base_cost + supp_cost + child_cost_total + eb_cost
    total_stay_sale = base_sale + supp_sale + child_sale_total + eb_sale

    # Taxes
    sale_tax, cost_tax = get_taxes(db, hotel_id, total_stay_sale, total_stay_cost)

    total_stay_cost += cost_tax

    # Contract margin
    contract = get_active_contract(db, hotel_id, checkin_date)
    company_cost = calc_company_cost(total_stay_sale, contract, sale_tax)

    return {
        "stay_cost": total_stay_cost,
        "company_cost": company_cost,
        "taxes": sale_tax,
        "cost_tax": cost_tax,
        "season_name_ar": season.name_ar if season else "",
        "season_name_en": season.name_en if season else "",
        "margin_type": contract.margin_type if contract else None,
        "margin_value": float(contract.margin_value) if contract else 0,
        "nights": nights,
        "base_cost_per_night": float(cost_per_night),
        "base_sale_per_night": float(sale_per_night),
        "extra_bed_cost": float(eb_cost),
        "extra_bed_sale": float(eb_sale),
        "single_supplement_cost": float(supp_cost),
        "single_supplement_sale": float(supp_sale),
        "child_cost": float(child_cost_total),
        "child_sale": float(child_sale_total),
    }
