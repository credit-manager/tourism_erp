"""Commission domain — CommissionPolicy, CommissionEntry."""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Date, DateTime, Numeric, ForeignKey
from sqlalchemy.orm import relationship
from models import Base
from currency_utils import DECIMAL_ZERO


class CommissionPolicy(Base):
    """سياسة عمولة قابلة لإعادة الاستخدام — بديل النسب المبعثرة."""
    __tablename__ = "commission_policies"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    commission_base = Column(String, default="profit")
    eligibility = Column(String, default="on_booking")
    role = Column(String, default="reservation_rep")
    rate_type = Column(String, default="percentage")
    rate_value = Column(Numeric(12,2), default=DECIMAL_ZERO)
    min_amount = Column(Numeric(12,2), default=DECIMAL_ZERO)
    max_amount = Column(Numeric(12,2), default=DECIMAL_ZERO)
    valid_from = Column(Date, nullable=True)
    valid_until = Column(Date, nullable=True)
    cancellation_effect = Column(String, default="forfeit")
    applies_to = Column(String, default="")
    is_active = Column(Integer, default=1)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class CommissionEntry(Base):
    """سجل عمولة لكل مستفيد — يتتبع الحالة من الحساب حتى الدفع أو الإلغاء."""
    __tablename__ = "commission_entries"
    id = Column(Integer, primary_key=True)
    policy_id = Column(Integer, ForeignKey("commission_policies.id"), nullable=True)
    reservation_id = Column(Integer, ForeignKey("reservations.id"), nullable=False)
    recipient_id = Column(Integer, nullable=False)
    recipient_type = Column(String, nullable=False)
    role = Column(String, default="reservation_rep")
    status = Column(String, default="calculated")
    base_amount = Column(Numeric(12,2), default=DECIMAL_ZERO)
    calculated_amount = Column(Numeric(12,2), default=DECIMAL_ZERO)
    earned_date = Column(DateTime, nullable=True)
    paid_date = Column(DateTime, nullable=True)
    paid_amount = Column(Numeric(12,2), nullable=True)
    reversed_date = Column(DateTime, nullable=True)
    reversed_reason = Column(String, nullable=True)
    linked_txn_id = Column(Integer, ForeignKey("treasury_transactions.id"), nullable=True)
    # accrued=1 يعني القيد المحاسبي (مدين عمولات / دائن ذمم دائنة) اتسجل
    # بالفعل وقت تأكيد الحجز (المصدر اليدوي القديم) — فلما تُدفع، القيد
    # المطلوب وقتها Dr AP / Cr Treasury بس (تسوية مستحق قائم)، مش قيد مصروف
    # جديد. accrued=0 يعني لسه معملهاش أي قيد (محرك السياسات) — فالدفع
    # بيعمل القيد الكامل (Dr Commission Expense / Cr Treasury) لأول مرة.
    accrued = Column(Integer, default=0)
    source = Column(String, default="policy")  # policy | legacy
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    policy = relationship("CommissionPolicy")
    reservation = relationship("Reservation")
    linked_txn = relationship("TreasuryTransaction", foreign_keys=[linked_txn_id])
