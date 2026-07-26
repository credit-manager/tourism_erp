"""مجال عقود المبيعات وعروض الأسعار والعمرة — Contract, Quotation, UmrahPackage, إلخ."""
import datetime
from decimal import Decimal
from sqlalchemy import Column, Integer, String, Date, Text, ForeignKey, Numeric, DateTime
from sqlalchemy.orm import relationship
from models import Base
from app.models.base import WorkflowMixin
from currency_utils import D, DECIMAL_ZERO


STAGES = ["Lead", "Qualified", "Quotation Sent", "Negotiation", "Won", "Lost"]


class Contract(Base):
    __tablename__ = "contracts"
    id = Column(Integer, primary_key=True)
    contract_number = Column(String, unique=True)
    created_date = Column(Date, default=datetime.date.today)
    title = Column(String, nullable=False)
    party_type = Column(String, default="supplier")
    supplier_id = Column(Integer, ForeignKey("suppliers.id"), nullable=True)
    hotel_id = Column(Integer, ForeignKey("hotels.id"), nullable=True)
    start_date = Column(Date)
    end_date = Column(Date)
    contract_value = Column(Numeric(12,2), default=DECIMAL_ZERO)
    status = Column(String, default="active")
    file_path = Column(String)
    notes = Column(Text)
    supplier = relationship("Supplier")
    hotel = relationship("Hotel")

    @property
    def is_expired(self):
        return bool(self.end_date and self.end_date < datetime.date.today())

    @property
    def days_remaining(self):
        if not self.end_date:
            return None
        return (self.end_date - datetime.date.today()).days

    @property
    def party_name(self):
        if self.party_type == "hotel" and self.hotel:
            return self.hotel.name
        if self.supplier:
            return self.supplier.name
        return "-"


def generate_contract_number(db):
    year = datetime.date.today().year
    count = db.query(Contract).count() + 1
    return f"CON-{year}-{count:04d}"


class Quotation(Base):
    __tablename__ = "quotations"
    id = Column(Integer, primary_key=True)
    quote_number = Column(String, unique=True, nullable=False)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False)
    validity_date = Column(Date)
    status = Column(String, default="draft")
    discount_type = Column(String, default="fixed")
    discount_value = Column(Numeric(12,2), default=DECIMAL_ZERO)
    tax_percentage = Column(Numeric(12,2), default=DECIMAL_ZERO)
    tax_amount = Column(Numeric(12,2), default=DECIMAL_ZERO)
    profit_margin = Column(Numeric(12,2), default=DECIMAL_ZERO)
    subtotal = Column(Numeric(12,2), default=DECIMAL_ZERO)
    grand_total = Column(Numeric(12,2), default=DECIMAL_ZERO)
    notes = Column(Text)
    terms_conditions = Column(Text)
    version = Column(Integer, default=1)
    reservation_id = Column(Integer, ForeignKey("reservations.id"), nullable=True)
    created_by = Column(String)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)
    customer = relationship("Customer")
    reservation = relationship("Reservation")
    items = relationship("QuotationLineItem", back_populates="quotation", cascade="all, delete-orphan", order_by="QuotationLineItem.id")


class QuotationLineItem(Base):
    __tablename__ = "quotation_line_items"
    id = Column(Integer, primary_key=True)
    quotation_id = Column(Integer, ForeignKey("quotations.id"), nullable=False)
    item_type = Column(String, nullable=False)
    description = Column(String)
    item_data = Column(Text)
    cost_price = Column(Numeric(12,2), default=DECIMAL_ZERO)
    sale_price = Column(Numeric(12,2), default=DECIMAL_ZERO)
    qty = Column(Integer, default=1)
    total = Column(Numeric(12,2), default=DECIMAL_ZERO)
    quotation = relationship("Quotation", back_populates="items")


class QuotationVersion(Base):
    __tablename__ = "quotation_versions"
    id = Column(Integer, primary_key=True)
    quotation_id = Column(Integer, ForeignKey("quotations.id"), nullable=False)
    version = Column(Integer, nullable=False)
    pdf_path = Column(String)
    snapshot = Column(Text)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    quotation = relationship("Quotation")


class UmrahPackage(Base):
    __tablename__ = "umrah_packages"
    id = Column(Integer, primary_key=True)
    package_number = Column(String, unique=True)
    created_date = Column(Date, default=datetime.date.today)
    pilgrim_name = Column(String, nullable=False)
    passport_no = Column(String)
    phone = Column(String)
    departure_date = Column(Date)
    return_date = Column(Date)
    hotel_makkah = Column(String)
    hotel_madinah = Column(String)
    cost_price = Column(Numeric(12,2), default=DECIMAL_ZERO)
    sale_price = Column(Numeric(12,2), default=DECIMAL_ZERO)
    paid_amount = Column(Numeric(12,2), default=DECIMAL_ZERO)
    currency_id = Column(Integer, ForeignKey("currencies.id"), nullable=True)
    amount_currency = Column(Numeric(12,2), default=DECIMAL_ZERO)
    amount_base = Column(Numeric(12,2), default=DECIMAL_ZERO)
    exchange_rate = Column(Numeric(12,6), default=D(1))
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=True)
    notes = Column(Text)
    employee = relationship("Employee")
    currency = relationship("Currency", foreign_keys=[currency_id])

    @property
    def profit(self):
        return D(self.sale_price) - D(self.cost_price)

    @property
    def remaining(self):
        return D(self.sale_price) - D(self.paid_amount)


def generate_umrah_number(db):
    year = datetime.date.today().year
    count = db.query(UmrahPackage).count() + 1
    return f"UMR-{year}-{count:04d}"
