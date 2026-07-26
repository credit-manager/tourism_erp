"""مجال النقل — Transport, Ticket."""
import datetime
from decimal import Decimal
from sqlalchemy import Column, Integer, String, Date, Text, ForeignKey, Numeric
from sqlalchemy.orm import relationship
from models import Base
from currency_utils import D, DECIMAL_ZERO


class Transport(Base):
    __tablename__ = "transports"
    id = Column(Integer, primary_key=True)
    created_date = Column(Date, default=datetime.date.today)
    vehicle_type = Column(String)
    plate_number = Column(String)
    driver_name = Column(String)
    driver_phone = Column(String)
    capacity = Column(Integer, default=0)
    supplier_id = Column(Integer, ForeignKey("suppliers.id"), nullable=True)
    trip_date = Column(Date)
    route = Column(String)
    cost = Column(Numeric(12,2), default=DECIMAL_ZERO)
    sale_price = Column(Numeric(12,2), default=DECIMAL_ZERO)
    currency_id = Column(Integer, ForeignKey("currencies.id"), nullable=True)
    amount_currency = Column(Numeric(12,2), default=DECIMAL_ZERO)
    amount_base = Column(Numeric(12,2), default=DECIMAL_ZERO)
    exchange_rate = Column(Numeric(12,6), default=D(1))
    notes = Column(Text)
    supplier = relationship("Supplier")
    currency = relationship("Currency", foreign_keys=[currency_id])

    @property
    def profit(self):
        return D(self.sale_price) - D(self.cost)


class Ticket(Base):
    __tablename__ = "tickets"
    id = Column(Integer, primary_key=True)
    ticket_number = Column(String, unique=True)
    created_date = Column(Date, default=datetime.date.today)
    passenger_name = Column(String, nullable=False)
    airline = Column(String)
    flight_number = Column(String)
    route = Column(String)
    departure_date = Column(Date)
    return_date = Column(Date)
    cost_price = Column(Numeric(12,2), default=DECIMAL_ZERO)
    sale_price = Column(Numeric(12,2), default=DECIMAL_ZERO)
    currency_id = Column(Integer, ForeignKey("currencies.id"), nullable=True)
    amount_currency = Column(Numeric(12,2), default=DECIMAL_ZERO)
    amount_base = Column(Numeric(12,2), default=DECIMAL_ZERO)
    exchange_rate = Column(Numeric(12,6), default=D(1))
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=True)
    status = Column(String, default="confirmed")
    notes = Column(Text)
    employee = relationship("Employee")
    currency = relationship("Currency", foreign_keys=[currency_id])

    @property
    def profit(self):
        return D(self.sale_price) - D(self.cost_price)


def generate_ticket_number(db):
    year = datetime.date.today().year
    count = db.query(Ticket).count() + 1
    return f"TKT-{year}-{count:04d}"
