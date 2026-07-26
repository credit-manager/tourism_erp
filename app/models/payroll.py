"""مجال الرواتب — PayrollRun, PayrollRunItem."""
from datetime import datetime
from decimal import Decimal
from sqlalchemy import Column, Integer, String, Date, DateTime, Numeric, ForeignKey
from sqlalchemy.orm import relationship
from models import Base
from currency_utils import DECIMAL_ZERO


class PayrollRun(Base):
    """شهرية رواتب محفوظة — تمنع إعادة الحساب."""
    __tablename__ = "payroll_runs"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    period_start = Column(Date, nullable=False)
    period_end = Column(Date, nullable=False)
    status = Column(String, default="draft")
    total_gross = Column(Numeric(12,2), default=DECIMAL_ZERO)
    total_deductions = Column(Numeric(12,2), default=DECIMAL_ZERO)
    total_net = Column(Numeric(12,2), default=DECIMAL_ZERO)
    notes = Column(String, nullable=True)
    created_by = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    reviewed_by = Column(String, nullable=True)
    reviewed_at = Column(DateTime, nullable=True)
    approved_by = Column(String, nullable=True)
    approved_at = Column(DateTime, nullable=True)
    paid_by = Column(String, nullable=True)
    paid_at = Column(DateTime, nullable=True)
    voucher_txn_id = Column(Integer, ForeignKey("treasury_transactions.id"), nullable=True)

    items = relationship("PayrollRunItem", back_populates="run", cascade="all, delete-orphan")
    voucher_txn = relationship("TreasuryTransaction", foreign_keys=[voucher_txn_id])


class PayrollRunItem(Base):
    """بند راتب موظف في شهرية — لقطة كاملة."""
    __tablename__ = "payroll_run_items"
    id = Column(Integer, primary_key=True)
    payroll_run_id = Column(Integer, ForeignKey("payroll_runs.id"), nullable=False)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False)
    basic_salary = Column(Numeric(12,2), default=DECIMAL_ZERO)
    housing_allowance = Column(Numeric(12,2), default=DECIMAL_ZERO)
    transport_allowance = Column(Numeric(12,2), default=DECIMAL_ZERO)
    other_allowances = Column(Numeric(12,2), default=DECIMAL_ZERO)
    overtime_amount = Column(Numeric(12,2), default=DECIMAL_ZERO)
    commission_amount = Column(Numeric(12,2), default=DECIMAL_ZERO)
    absence_deduction = Column(Numeric(12,2), default=DECIMAL_ZERO)
    late_deduction = Column(Numeric(12,2), default=DECIMAL_ZERO)
    advances_deduction = Column(Numeric(12,2), default=DECIMAL_ZERO)
    social_insurance = Column(Numeric(12,2), default=DECIMAL_ZERO)
    other_deductions = Column(Numeric(12,2), default=DECIMAL_ZERO)
    gross_pay = Column(Numeric(12,2), default=DECIMAL_ZERO)
    total_deductions = Column(Numeric(12,2), default=DECIMAL_ZERO)
    net_pay = Column(Numeric(12,2), default=DECIMAL_ZERO)
    notes = Column(String, nullable=True)

    run = relationship("PayrollRun", back_populates="items")
    employee = relationship("Employee")
