"""مجال العملاء — Customer, CustomerContact, CustomerQuote, CustomerTask, CustomerComplaint, CustomerTimeline, SalesOpportunity."""
import datetime
from sqlalchemy import Column, Integer, String, Date, DateTime, Text, ForeignKey, Numeric
from sqlalchemy.orm import relationship
from models import Base
from currency_utils import DECIMAL_ZERO


class Customer(Base):
    __tablename__ = "customers"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    type = Column(String, default="B2C")  # B2C or B2B
    phone = Column(String)
    email = Column(String)
    address = Column(String)
    city = Column(String)
    country = Column(String)
    nationality = Column(String)
    gender = Column(String)  # male / female
    date_of_birth = Column(Date)
    id_number = Column(String)
    passport_no = Column(String)
    balance = Column(Numeric(12,2), default=DECIMAL_ZERO)
    notes = Column(Text)
    classification = Column(String, default="regular")  # vip / gold / silver / regular
    source = Column(String, default="direct")  # direct / facebook / referral / advertisement / walk_in / other
    account_manager_id = Column(Integer, ForeignKey("employees.id"), nullable=True)
    clv = Column(Numeric(12,2), default=DECIMAL_ZERO)
    risk_level = Column(String, default="low")  # low / medium / high
    credit_limit = Column(Numeric(12,2), default=DECIMAL_ZERO)
    payment_terms = Column(String, default="due_on_receipt")  # due_on_receipt / net_15 / net_30 / net_60 / custom
    last_contact_date = Column(Date)
    preferred_contact_method = Column(String, default="phone")  # phone / email / whatsapp
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    account_manager = relationship("Employee")
    bookings = relationship("Booking", back_populates="customer")
    travel_agent_reservations = relationship("Reservation", back_populates="travel_agent", foreign_keys="Reservation.travel_agent_id")
    contacts = relationship("CustomerContact", back_populates="customer", cascade="all, delete-orphan")
    quotes = relationship("CustomerQuote", back_populates="customer", cascade="all, delete-orphan")
    tasks = relationship("CustomerTask", back_populates="customer", cascade="all, delete-orphan")
    complaints = relationship("CustomerComplaint", back_populates="customer", cascade="all, delete-orphan")
    timeline = relationship("CustomerTimeline", back_populates="customer", cascade="all, delete-orphan")
    quotations = relationship("Quotation", back_populates="customer")


class CustomerContact(Base):
    __tablename__ = "customer_contacts"
    id = Column(Integer, primary_key=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False)
    name = Column(String, nullable=False)
    phone = Column(String)
    email = Column(String)
    job_title = Column(String)
    is_primary = Column(Integer, default=0)
    notes = Column(Text)
    customer = relationship("Customer", back_populates="contacts")


class CustomerQuote(Base):
    __tablename__ = "customer_quotes"
    id = Column(Integer, primary_key=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False)
    quote_number = Column(String, unique=True)
    date = Column(Date, default=datetime.date.today)
    total_amount = Column(Numeric(12,2), default=DECIMAL_ZERO)
    status = Column(String, default="draft")  # draft / sent / accepted / rejected
    valid_until = Column(Date)
    notes = Column(Text)
    created_by = Column(String)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    customer = relationship("Customer", back_populates="quotes")


class CustomerTask(Base):
    __tablename__ = "customer_tasks"
    id = Column(Integer, primary_key=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False)
    title = Column(String, nullable=False)
    description = Column(Text)
    due_date = Column(Date)
    status = Column(String, default="pending")  # pending / in_progress / completed / cancelled
    assigned_to_id = Column(Integer, ForeignKey("employees.id"), nullable=True)
    priority = Column(String, default="normal")  # low / normal / high / urgent
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    completed_at = Column(DateTime)
    customer = relationship("Customer", back_populates="tasks")
    assigned_to = relationship("Employee")


class CustomerComplaint(Base):
    __tablename__ = "customer_complaints"
    id = Column(Integer, primary_key=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False)
    subject = Column(String, nullable=False)
    description = Column(Text)
    status = Column(String, default="open")  # open / in_progress / resolved / closed
    resolution = Column(Text)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    resolved_at = Column(DateTime)
    created_by = Column(String)
    customer = relationship("Customer", back_populates="complaints")


class CustomerTimeline(Base):
    __tablename__ = "customer_timeline"
    id = Column(Integer, primary_key=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False)
    type = Column(String)  # note / call / email / meeting / reservation / collection / quote / task / complaint / system
    content = Column(Text)
    reference_type = Column(String)  # reservation / collection / quote / task / complaint
    reference_id = Column(Integer)
    created_by = Column(String)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    customer = relationship("Customer", back_populates="timeline")


class SalesOpportunity(Base):
    __tablename__ = "sales_opportunities"
    id = Column(Integer, primary_key=True)
    stage = Column(String, default="Lead")  # Lead / Qualified / Quotation Sent / Negotiation / Won / Lost
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False)
    source = Column(String, default="direct")
    destination = Column(String)
    budget = Column(Numeric(12,2), default=DECIMAL_ZERO)
    travel_date = Column(Date)
    travelers_count = Column(Integer, default=1)
    probability = Column(Integer, default=50)  # 0-100
    expected_value = Column(Numeric(12,2), default=DECIMAL_ZERO)
    sales_rep_id = Column(Integer, ForeignKey("employees.id"), nullable=True)
    next_followup_date = Column(Date)
    loss_reason = Column(Text)
    notes = Column(Text)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    customer = relationship("Customer")
    sales_rep = relationship("Employee")
