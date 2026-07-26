"""Bank domain — BankStatement, BankTransaction."""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Date, DateTime, Numeric, ForeignKey
from sqlalchemy.orm import relationship
from models import Base
from currency_utils import DECIMAL_ZERO


class BankStatement(Base):
    """كشف حساب بنكي مستورد (مرة واحدة لكل فترة)"""
    __tablename__ = "bank_statements"
    id = Column(Integer, primary_key=True)
    account_id = Column(Integer, ForeignKey("treasury_accounts.id"), nullable=False)
    period_start = Column(Date, nullable=True)
    period_end = Column(Date, nullable=True)
    opening_balance = Column(Numeric(12,2), default=DECIMAL_ZERO)
    closing_balance = Column(Numeric(12,2), default=DECIMAL_ZERO)
    file_path = Column(String)
    status = Column(String, default="imported")
    created_at = Column(DateTime, default=datetime.utcnow)
    created_by = Column(String, nullable=True)
    account = relationship("TreasuryAccount", foreign_keys=[account_id])
    transactions = relationship("BankTransaction", back_populates="statement", lazy="dynamic")


class BankTransaction(Base):
    """حركة واحدة من كشف الحساب البنكي"""
    __tablename__ = "bank_transactions"
    id = Column(Integer, primary_key=True)
    statement_id = Column(Integer, ForeignKey("bank_statements.id"), nullable=False)
    date = Column(Date, nullable=False)
    description = Column(String)
    reference = Column(String, nullable=True, index=True)
    debit = Column(Numeric(12,2), default=DECIMAL_ZERO)
    credit = Column(Numeric(12,2), default=DECIMAL_ZERO)
    balance = Column(Numeric(12,2), nullable=True)
    matched_txn_id = Column(Integer, ForeignKey("treasury_transactions.id"), nullable=True)
    match_status = Column(String, default="unmatched")
    notes = Column(String)
    statement = relationship("BankStatement", back_populates="transactions")
    matched_txn = relationship("TreasuryTransaction", foreign_keys=[matched_txn_id])
