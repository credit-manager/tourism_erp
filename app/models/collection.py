"""مجال التحصيل — Collection, CollectionAllocation."""
import datetime
from decimal import Decimal
from sqlalchemy import Column, Integer, String, Date, Text, ForeignKey, Numeric
from sqlalchemy.orm import relationship
from models import Base
from app.models.base import WorkflowMixin
from currency_utils import D, DECIMAL_ZERO


class Collection(WorkflowMixin, Base):
    __tablename__ = "collections"
    id = Column(Integer, primary_key=True)
    collection_number = Column(String, unique=True)
    date = Column(Date, default=datetime.date.today)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True)
    payer_name = Column(String)
    total_amount = Column(Numeric(12,2), default=DECIMAL_ZERO)
    allocated_amount = Column(Numeric(12,2), default=DECIMAL_ZERO)
    unallocated_amount = Column(Numeric(12,2), default=DECIMAL_ZERO)
    notes = Column(Text)
    account_id = Column(Integer, ForeignKey("treasury_accounts.id"), nullable=True)
    currency_id = Column(Integer, ForeignKey("currencies.id"), nullable=True)
    amount_currency = Column(Numeric(12,2), default=DECIMAL_ZERO)
    amount_base = Column(Numeric(12,2), default=DECIMAL_ZERO)
    exchange_rate = Column(Numeric(12,6), default=Decimal("1.0"))

    customer = relationship("Customer")
    account = relationship("TreasuryAccount", foreign_keys=[account_id])
    currency = relationship("Currency")
    allocations = relationship("CollectionAllocation", back_populates="collection")


class CollectionAllocation(Base):
    __tablename__ = "collection_allocations"
    id = Column(Integer, primary_key=True)
    collection_id = Column(Integer, ForeignKey("collections.id"))
    reservation_id = Column(Integer, ForeignKey("reservations.id"))
    amount = Column(Numeric(12,2), default=DECIMAL_ZERO)
    date = Column(Date, default=datetime.date.today)

    collection = relationship("Collection", back_populates="allocations")
    reservation = relationship("Reservation", back_populates="collection_allocations")


def generate_collection_number(db):
    year = datetime.date.today().year
    count = db.query(Collection).count() + 1
    return f"COL-{year}-{count:04d}"
