"""مجال الفنادق — Hotel, RoomType, MealPlan, HotelContract, PriceSeason, إلخ."""
from sqlalchemy import Column, Integer, String, Date, Text, ForeignKey, Numeric
from sqlalchemy.orm import relationship
from models import Base
from currency_utils import DECIMAL_ZERO


class Hotel(Base):
    __tablename__ = "hotels"
    id = Column(Integer, primary_key=True)
    supplier_id = Column(Integer, ForeignKey("suppliers.id"))
    name = Column(String, nullable=False)
    city = Column(String)
    price_per_night = Column(Numeric(12,2), default=DECIMAL_ZERO)
    available_rooms = Column(Integer, default=0)
    supplier = relationship("Supplier", back_populates="hotels")


class RoomType(Base):
    __tablename__ = "room_types"
    id = Column(Integer, primary_key=True)
    hotel_id = Column(Integer, ForeignKey("hotels.id"), nullable=False)
    name_ar = Column(String, nullable=False)
    name_en = Column(String, nullable=False)
    max_guests = Column(Integer, default=2)
    description = Column(Text)
    sort_order = Column(Integer, default=0)
    hotel = relationship("Hotel", backref="room_types")
    season_prices = relationship("SeasonRoomPrice", back_populates="room_type", cascade="all, delete-orphan")


class MealPlan(Base):
    __tablename__ = "meal_plans"
    id = Column(Integer, primary_key=True)
    hotel_id = Column(Integer, ForeignKey("hotels.id"), nullable=False)
    code = Column(String, nullable=False)  # RO, BB, HB, FB, AI
    name_ar = Column(String, nullable=False)
    name_en = Column(String, nullable=False)
    price_per_person_night = Column(Numeric(12,2), default=DECIMAL_ZERO)
    hotel = relationship("Hotel", backref="meal_plans")


class HotelContract(Base):
    __tablename__ = "hotel_contracts"
    id = Column(Integer, primary_key=True)
    hotel_id = Column(Integer, ForeignKey("hotels.id"), nullable=False)
    name = Column(String, nullable=False)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    margin_type = Column(String, default="fixed")  # percentage / fixed
    margin_value = Column(Numeric(12,2), default=DECIMAL_ZERO)
    currency = Column(String, default="EGP")
    notes = Column(Text)
    is_active = Column(Integer, default=1)
    hotel = relationship("Hotel", backref="contracts")


class PriceSeason(Base):
    __tablename__ = "price_seasons"
    id = Column(Integer, primary_key=True)
    hotel_id = Column(Integer, ForeignKey("hotels.id"), nullable=False)
    name_ar = Column(String, nullable=False)
    name_en = Column(String, nullable=False)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    priority = Column(Integer, default=0)
    hotel = relationship("Hotel", backref="seasons")
    room_prices = relationship("SeasonRoomPrice", back_populates="season", cascade="all, delete-orphan")
    child_prices = relationship("SeasonChildPrice", back_populates="season", cascade="all, delete-orphan")
    extra_bed_prices = relationship("SeasonExtraBedPrice", back_populates="season", cascade="all, delete-orphan")
    single_supplements = relationship("SeasonSingleSupplement", back_populates="season", cascade="all, delete-orphan")


class SeasonRoomPrice(Base):
    __tablename__ = "season_room_prices"
    id = Column(Integer, primary_key=True)
    season_id = Column(Integer, ForeignKey("price_seasons.id"), nullable=False)
    room_type_id = Column(Integer, ForeignKey("room_types.id"), nullable=False)
    cost_per_night = Column(Numeric(12,2), default=DECIMAL_ZERO)
    sale_per_night = Column(Numeric(12,2), default=DECIMAL_ZERO)
    season = relationship("PriceSeason", back_populates="room_prices")
    room_type = relationship("RoomType", back_populates="season_prices")


class SeasonChildPrice(Base):
    __tablename__ = "season_child_prices"
    id = Column(Integer, primary_key=True)
    season_id = Column(Integer, ForeignKey("price_seasons.id"), nullable=False)
    room_type_id = Column(Integer, ForeignKey("room_types.id"), nullable=False)
    age_from = Column(Integer, default=0)
    age_to = Column(Integer, default=99)
    price_type = Column(String, default="percentage")  # free / percentage / fixed
    price_value = Column(Numeric(12,2), default=DECIMAL_ZERO)
    season = relationship("PriceSeason", back_populates="child_prices")


class SeasonExtraBedPrice(Base):
    __tablename__ = "season_extra_bed_prices"
    id = Column(Integer, primary_key=True)
    season_id = Column(Integer, ForeignKey("price_seasons.id"), nullable=False)
    room_type_id = Column(Integer, ForeignKey("room_types.id"), nullable=False)
    cost = Column(Numeric(12,2), default=DECIMAL_ZERO)
    sale = Column(Numeric(12,2), default=DECIMAL_ZERO)
    season = relationship("PriceSeason", back_populates="extra_bed_prices")


class SeasonSingleSupplement(Base):
    __tablename__ = "season_single_supplements"
    id = Column(Integer, primary_key=True)
    season_id = Column(Integer, ForeignKey("price_seasons.id"), nullable=False)
    room_type_id = Column(Integer, ForeignKey("room_types.id"), nullable=False)
    cost = Column(Numeric(12,2), default=DECIMAL_ZERO)
    sale = Column(Numeric(12,2), default=DECIMAL_ZERO)
    season = relationship("PriceSeason", back_populates="single_supplements")


class NationalityPricing(Base):
    __tablename__ = "nationality_pricings"
    id = Column(Integer, primary_key=True)
    hotel_id = Column(Integer, ForeignKey("hotels.id"), nullable=False)
    nationality = Column(String, nullable=False)
    season_id = Column(Integer, ForeignKey("price_seasons.id"), nullable=True)
    room_type_id = Column(Integer, ForeignKey("room_types.id"), nullable=True)
    sale_per_night = Column(Numeric(12,2), nullable=True)
    cost_per_night = Column(Numeric(12,2), nullable=True)
    extra_bed_sale = Column(Numeric(12,2), nullable=True)
    extra_bed_cost = Column(Numeric(12,2), nullable=True)
    child_price_type = Column(String, nullable=True)
    child_price_value = Column(Numeric(12,2), nullable=True)
    single_supplement_sale = Column(Numeric(12,2), nullable=True)
    single_supplement_cost = Column(Numeric(12,2), nullable=True)
    hotel = relationship("Hotel", backref="nationality_pricings")


class BlackoutDate(Base):
    __tablename__ = "blackout_dates"
    id = Column(Integer, primary_key=True)
    hotel_id = Column(Integer, ForeignKey("hotels.id"), nullable=False)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    reason = Column(String)
    hotel = relationship("Hotel", backref="blackout_dates")


class MinimumStay(Base):
    __tablename__ = "minimum_stays"
    id = Column(Integer, primary_key=True)
    hotel_id = Column(Integer, ForeignKey("hotels.id"), nullable=False)
    season_id = Column(Integer, ForeignKey("price_seasons.id"), nullable=True)
    min_nights = Column(Integer, default=1)
    start_date = Column(Date, nullable=True)
    end_date = Column(Date, nullable=True)
    hotel = relationship("Hotel", backref="minimum_stays")


class CancellationPolicy(Base):
    __tablename__ = "cancellation_policies"
    id = Column(Integer, primary_key=True)
    hotel_id = Column(Integer, ForeignKey("hotels.id"), nullable=False)
    days_before_checkin = Column(Integer, nullable=False)
    refund_percent = Column(Numeric(12,2), default=DECIMAL_ZERO)
    fee_percent = Column(Numeric(12,2), default=DECIMAL_ZERO)
    hotel = relationship("Hotel", backref="cancellation_policies")


class HotelTax(Base):
    __tablename__ = "hotel_taxes"
    id = Column(Integer, primary_key=True)
    hotel_id = Column(Integer, ForeignKey("hotels.id"), nullable=False)
    name_ar = Column(String, nullable=False)
    name_en = Column(String, nullable=False)
    tax_type = Column(String, default="percentage")
    value = Column(Numeric(12,2), default=DECIMAL_ZERO)
    applies_to = Column(String, default="sale")
    hotel = relationship("Hotel", backref="taxes")
