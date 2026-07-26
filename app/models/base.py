"""Base, engine, SessionLocal, WorkflowMixin, Currency, ExchangeRate, _SysCfg — no circular deps."""
import datetime
from decimal import Decimal
from sqlalchemy import create_engine, Column, Integer, String, Date, DateTime, Numeric, UniqueConstraint, ForeignKey
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
from currency_utils import D, DECIMAL_ZERO

DATABASE_URL = "sqlite:///tourism_erp.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()


class WorkflowMixin:
    status = Column(String, default="draft")
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    created_by = Column(String, nullable=True)
    reviewed_at = Column(DateTime, nullable=True)
    reviewed_by = Column(String, nullable=True)
    approved_at = Column(DateTime, nullable=True)
    approved_by = Column(String, nullable=True)
    posted_at = Column(DateTime, nullable=True)
    posted_by = Column(String, nullable=True)
    cancelled_at = Column(DateTime, nullable=True)
    cancelled_by = Column(String, nullable=True)
    cancellation_reason = Column(String, nullable=True)


class Currency(Base):
    __tablename__ = "currencies"
    id = Column(Integer, primary_key=True)
    code = Column(String, unique=True, nullable=False)
    name = Column(String)
    symbol = Column(String)
    exchange_rate = Column(Numeric(12,6), default=Decimal("1.0"))
    is_base = Column(Integer, default=0)


class ExchangeRate(Base):
    __tablename__ = "exchange_rates"
    id = Column(Integer, primary_key=True)
    currency_id = Column(Integer, ForeignKey("currencies.id"), nullable=False)
    date = Column(Date, nullable=False)
    buy_rate = Column(Numeric(12,6), default=Decimal("1.0"))
    sell_rate = Column(Numeric(12,6), default=Decimal("1.0"))
    currency = relationship("Currency")
    __table_args__ = (UniqueConstraint("currency_id", "date"),)


class _SysCfg(Base):
    __tablename__ = "_scfg"
    k = Column(String, primary_key=True)
    v = Column(String, default="")
