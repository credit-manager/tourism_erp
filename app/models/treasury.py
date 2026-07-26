"""مجال الخزنة — TreasuryAccount, DefaultTreasuryAccount, TreasuryTransfer, CashClosing, TreasuryTransaction, Expense."""
import datetime
from decimal import Decimal
from sqlalchemy import Column, Integer, String, Date, Text, ForeignKey, Numeric, Boolean
from sqlalchemy.orm import relationship
from models import Base
from app.models.base import WorkflowMixin
from currency_utils import DECIMAL_ZERO


class TreasuryAccount(Base):
    __tablename__ = "treasury_accounts"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    type = Column(String, default="treasury")
    balance = Column(Numeric(12,2), default=DECIMAL_ZERO)
    allow_negative_balance = Column(Boolean, default=False)
    currency_id = Column(Integer, ForeignKey("currencies.id"), nullable=True)
    currency = relationship("Currency")
    transactions = relationship("TreasuryTransaction", back_populates="account")


class DefaultTreasuryAccount(Base):
    __tablename__ = "default_treasury_accounts"
    id = Column(Integer, primary_key=True)
    operation_type = Column(String, nullable=False)
    branch = Column(String, default="main")
    account_id = Column(Integer, ForeignKey("treasury_accounts.id"), nullable=False)
    account = relationship("TreasuryAccount", foreign_keys=[account_id])


class TreasuryTransfer(WorkflowMixin, Base):
    __tablename__ = "treasury_transfers"
    id = Column(Integer, primary_key=True)
    from_account_id = Column(Integer, ForeignKey("treasury_accounts.id"), nullable=False)
    to_account_id = Column(Integer, ForeignKey("treasury_accounts.id"), nullable=False)
    amount = Column(Numeric(12,2), default=DECIMAL_ZERO)
    converted_amount = Column(Numeric(12,2), default=DECIMAL_ZERO)
    exchange_rate = Column(Numeric(12,6), default=1.0)
    fee = Column(Numeric(12,2), default=DECIMAL_ZERO)
    net_amount = Column(Numeric(12,2), default=DECIMAL_ZERO)
    description = Column(String)
    date = Column(Date, default=datetime.date.today)
    from_account = relationship("TreasuryAccount", foreign_keys=[from_account_id])
    to_account = relationship("TreasuryAccount", foreign_keys=[to_account_id])


class CashClosing(WorkflowMixin, Base):
    __tablename__ = "cash_closings"
    id = Column(Integer, primary_key=True)
    account_id = Column(Integer, ForeignKey("treasury_accounts.id"), nullable=False)
    closing_date = Column(Date, nullable=False)
    system_balance = Column(Numeric(12,2), default=DECIMAL_ZERO)
    actual_balance = Column(Numeric(12,2), default=DECIMAL_ZERO)
    difference = Column(Numeric(12,2), default=DECIMAL_ZERO)
    reason = Column(String)
    attachment_path = Column(String)
    account = relationship("TreasuryAccount")


class TreasuryTransaction(WorkflowMixin, Base):
    __tablename__ = "treasury_transactions"
    id = Column(Integer, primary_key=True)
    account_id = Column(Integer, ForeignKey("treasury_accounts.id"))
    booking_id = Column(Integer, ForeignKey("bookings.id"), nullable=True)
    type = Column(String)
    amount = Column(Numeric(12,2), default=DECIMAL_ZERO)
    amount_currency = Column(Numeric(12,2), default=DECIMAL_ZERO)
    amount_base = Column(Numeric(12,2), default=DECIMAL_ZERO)
    exchange_rate = Column(Numeric(12,6), default=Decimal("1.0"))
    currency_id = Column(Integer, ForeignKey("currencies.id"), nullable=True)
    description = Column(String)
    reference = Column(String, nullable=True, index=True)
    date = Column(Date, default=datetime.date.today)
    account = relationship("TreasuryAccount", back_populates="transactions")
    currency = relationship("Currency")


class Expense(WorkflowMixin, Base):
    __tablename__ = "expenses"
    id = Column(Integer, primary_key=True)
    category = Column(String)
    amount = Column(Numeric(12,2), default=DECIMAL_ZERO)
    date = Column(Date, default=datetime.date.today)
    description = Column(String)
    account_id = Column(Integer, ForeignKey("treasury_accounts.id"), nullable=True)
    currency_id = Column(Integer, ForeignKey("currencies.id"), nullable=True)
    amount_currency = Column(Numeric(12,2), default=DECIMAL_ZERO)
    amount_base = Column(Numeric(12,2), default=DECIMAL_ZERO)
    exchange_rate = Column(Numeric(12,6), default=Decimal("1.0"))
    account = relationship("TreasuryAccount", foreign_keys=[account_id])
    currency = relationship("Currency")
