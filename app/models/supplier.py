"""مجال الموردين — Supplier, SupplierPayment, SupplierPaymentAllocation, SupplierConfirmation, SupplierConfirmationLine, SupplierInvoice, SupplierInvoiceLine."""
import datetime
from decimal import Decimal
from sqlalchemy import Column, Integer, String, Date, DateTime, Text, ForeignKey, Numeric
from sqlalchemy.orm import relationship
from models import Base
from app.models.base import WorkflowMixin
from currency_utils import D, DECIMAL_ZERO


class Supplier(Base):
    __tablename__ = "suppliers"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    type = Column(String, default="hotel")  # hotel / transport / guide / local_company
    phone = Column(String)
    balance = Column(Numeric(12,2), default=DECIMAL_ZERO)
    hotels = relationship("Hotel", back_populates="supplier")
    bookings = relationship("Booking", back_populates="supplier")


class SupplierPayment(WorkflowMixin, Base):
    __tablename__ = "supplier_payments"
    id = Column(Integer, primary_key=True)
    payment_number = Column(String, unique=True)
    date = Column(Date, default=datetime.date.today)
    supplier_id = Column(Integer, ForeignKey("suppliers.id"), nullable=False)
    total_amount = Column(Numeric(12,2), default=DECIMAL_ZERO)
    allocated_amount = Column(Numeric(12,2), default=DECIMAL_ZERO)
    unallocated_amount = Column(Numeric(12,2), default=DECIMAL_ZERO)
    notes = Column(Text)
    account_id = Column(Integer, ForeignKey("treasury_accounts.id"), nullable=True)
    currency_id = Column(Integer, ForeignKey("currencies.id"), nullable=True)
    amount_currency = Column(Numeric(12,2), default=DECIMAL_ZERO)
    amount_base = Column(Numeric(12,2), default=DECIMAL_ZERO)
    exchange_rate = Column(Numeric(12,6), default=Decimal("1.0"))

    supplier = relationship("Supplier")
    account = relationship("TreasuryAccount", foreign_keys=[account_id])
    currency = relationship("Currency")
    allocations = relationship("SupplierPaymentAllocation", back_populates="payment")


class SupplierPaymentAllocation(Base):
    __tablename__ = "supplier_payment_allocations"
    id = Column(Integer, primary_key=True)
    payment_id = Column(Integer, ForeignKey("supplier_payments.id"))
    reservation_id = Column(Integer, ForeignKey("reservations.id"))
    amount = Column(Numeric(12,2), default=DECIMAL_ZERO)
    date = Column(Date, default=datetime.date.today)

    payment = relationship("SupplierPayment", back_populates="allocations")
    reservation = relationship("Reservation")


class SupplierConfirmation(Base):
    __tablename__ = "supplier_confirmations"
    id = Column(Integer, primary_key=True)
    confirmation_number = Column(String, unique=True, nullable=False)
    supplier_id = Column(Integer, ForeignKey("suppliers.id"), nullable=False)
    confirmation_date = Column(Date, default=datetime.date.today)
    currency_id = Column(Integer, ForeignKey("currencies.id"), nullable=True)
    amount_currency = Column(Numeric(12,2), default=DECIMAL_ZERO)
    amount_base = Column(Numeric(12,2), default=DECIMAL_ZERO)
    exchange_rate = Column(Numeric(12,6), default=D(1))
    status = Column(String, default="draft")
    notes = Column(Text)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    created_by = Column(String, nullable=True)
    confirmed_at = Column(DateTime, nullable=True)
    confirmed_by = Column(String, nullable=True)

    supplier = relationship("Supplier")
    currency = relationship("Currency", foreign_keys=[currency_id])
    lines = relationship("SupplierConfirmationLine", back_populates="confirmation", cascade="all, delete-orphan")


class SupplierConfirmationLine(Base):
    __tablename__ = "supplier_confirmation_lines"
    id = Column(Integer, primary_key=True)
    confirmation_id = Column(Integer, ForeignKey("supplier_confirmations.id"), nullable=False)
    reservation_id = Column(Integer, ForeignKey("reservations.id"), nullable=False)
    confirmed_cost = Column(Numeric(12,2), default=DECIMAL_ZERO)
    notes = Column(Text)

    confirmation = relationship("SupplierConfirmation", back_populates="lines")
    reservation = relationship("Reservation")


class SupplierInvoice(WorkflowMixin, Base):
    __tablename__ = "supplier_invoices"
    id = Column(Integer, primary_key=True)
    invoice_number = Column(String, unique=True, nullable=False)
    supplier_id = Column(Integer, ForeignKey("suppliers.id"), nullable=False)
    invoice_date = Column(Date, default=datetime.date.today)
    due_date = Column(Date, nullable=True)
    reference_number = Column(String, nullable=True)
    currency_id = Column(Integer, ForeignKey("currencies.id"), nullable=True)
    amount_currency = Column(Numeric(12,2), default=DECIMAL_ZERO)
    amount_base = Column(Numeric(12,2), default=DECIMAL_ZERO)
    exchange_rate = Column(Numeric(12,6), default=D(1))
    total_before_tax = Column(Numeric(12,2), default=DECIMAL_ZERO)
    tax_amount = Column(Numeric(12,2), default=DECIMAL_ZERO)
    discount_amount = Column(Numeric(12,2), default=DECIMAL_ZERO)
    total_amount = Column(Numeric(12,2), default=DECIMAL_ZERO)
    notes = Column(Text)

    supplier = relationship("Supplier")
    currency = relationship("Currency", foreign_keys=[currency_id])
    lines = relationship("SupplierInvoiceLine", back_populates="invoice", cascade="all, delete-orphan")


class SupplierInvoiceLine(Base):
    __tablename__ = "supplier_invoice_lines"
    id = Column(Integer, primary_key=True)
    invoice_id = Column(Integer, ForeignKey("supplier_invoices.id"), nullable=False)
    reservation_id = Column(Integer, ForeignKey("reservations.id"), nullable=True)
    confirmation_line_id = Column(Integer, ForeignKey("supplier_confirmation_lines.id"), nullable=True)
    description = Column(String, default="")
    expected_cost = Column(Numeric(12,2), default=DECIMAL_ZERO)
    confirmed_cost = Column(Numeric(12,2), default=DECIMAL_ZERO)
    invoiced_cost = Column(Numeric(12,2), default=DECIMAL_ZERO)
    cost_difference = Column(Numeric(12,2), default=DECIMAL_ZERO)
    tax_amount = Column(Numeric(12,2), default=DECIMAL_ZERO)
    discount_amount = Column(Numeric(12,2), default=DECIMAL_ZERO)
    net_amount = Column(Numeric(12,2), default=DECIMAL_ZERO)
    notes = Column(Text)

    invoice = relationship("SupplierInvoice", back_populates="lines")
    reservation = relationship("Reservation")
    confirmation_line = relationship("SupplierConfirmationLine")


def generate_supplier_payment_number(db):
    year = datetime.date.today().year
    count = db.query(SupplierPayment).count() + 1
    return f"SPAY-{year}-{count:04d}"


def generate_invoice_number(db):
    year = datetime.date.today().year
    count = db.query(SupplierInvoice).count() + 1
    return f"SI-{year}-{count:05d}"


def generate_confirmation_number(db):
    year = datetime.date.today().year
    count = db.query(SupplierConfirmation).count() + 1
    return f"SC-{year}-{count:05d}"
