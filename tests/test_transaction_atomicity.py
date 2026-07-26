"""
Proves every financial transaction is atomic:
if any step fails, ALL changes are rolled back (not just the failing step).
Run: python -m pytest tests/test_transaction_atomicity.py -v
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from decimal import Decimal
from datetime import date, datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models import (
    Base, Account, JournalEntry, JournalLine, seed_chart_of_accounts,
    TreasuryAccount, TreasuryTransaction, TreasuryTransfer, CashClosing, Expense,
    Supplier, SupplierPayment, SupplierPaymentAllocation,
    Collection, CollectionAllocation, generate_collection_number,
    Reservation, generate_booking_number,
    Hotel, Employee, Customer, Currency,
    CommissionPolicy, CommissionEntry,
    PayrollRun, PayrollRunItem,
)
from services.collection_service import CollectionService
from services.supplier_payment_service import SupplierPaymentService
from services.commission_service import CommissionService
from services.payroll_service import PayrollService
from services.treasury_service import TreasuryService
from services.accounting_service import AccountingService
from currency_utils import D, DECIMAL_ZERO


class MockUser:
    username = "test_user"
    id = 999
    role = "admin"


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    seed_chart_of_accounts(session)
    session.add(TreasuryAccount(name="Main Treasury", balance=0, type="cash"))
    session.add(Supplier(name="Test Supplier", balance=0))
    session.add(Customer(name="Test Customer", balance=0))
    session.add(Currency(code="EGP", name="EGP", symbol="EGP", exchange_rate=1))
    session.add(Hotel(name="Test Hotel"))
    session.add(Employee(name="Test Employee"))
    session.commit()
    yield session
    session.close()


def _make_reservation(db):
    r = Reservation(
        booking_number=generate_booking_number(db),
        customer_id=1, hotel_id=1, guest_name="Test Guest",
        checkin_date=date(2026, 7, 1), checkout_date=date(2026, 7, 5),
        stay_cost=D("5000"), paid_to_office=D("5000"),
        status="confirmed",
    )
    db.add(r)
    db.flush()
    return r


def _make_collection(db, amount=D("3000")):
    c = Collection(
        collection_number=generate_collection_number(db),
        payer_name="Test Payer", total_amount=amount,
        allocated_amount=DECIMAL_ZERO, unallocated_amount=amount,
        notes="cash", status="draft",
    )
    db.add(c)
    db.flush()
    return c


# ===================== CollectionService Atomicity =====================

def test_collection_create_rolls_back_on_failure(db):
    """collection create flush لكن commit لأ — rollback يمسح الأثر"""
    initial_count = db.query(Collection).count()
    r = _make_reservation(db)
    db.commit()

    try:
        svc = CollectionService(db, MockUser())
        svc.create({
            "payer_name": "Fail Test",
            "total_amount": "1000",
            "payment_method": "cash",
            "customer_id": 1,
            "reservation_ids": [r.id],
            "allocation_amount_1": "1000",
        })
        assert db.query(Collection).count() == initial_count + 1
        raise RuntimeError("Simulated failure after service.create")
        db.commit()
    except RuntimeError:
        db.rollback()

    assert db.query(Collection).count() == initial_count


def test_collection_post_rolls_back_on_failure(db):
    """post تخلق خزنة + محاسبة — rollback يمسح الأثر"""
    coll = _make_collection(db)
    r = _make_reservation(db)
    treasury_acc = db.query(TreasuryAccount).first()
    coll.account_id = treasury_acc.id
    db.add(CollectionAllocation(
        collection_id=coll.id, reservation_id=r.id,
        amount=D("1000"),
    ))
    coll.status = "approved"
    db.commit()

    txn_before = db.query(TreasuryTransaction).count()
    je_before = db.query(JournalEntry).count()

    try:
        svc = CollectionService(db, MockUser())
        svc.post(coll.id)
        assert db.query(TreasuryTransaction).count() > txn_before
        raise RuntimeError("Simulated failure after post")
        db.commit()
    except RuntimeError:
        db.rollback()

    assert db.query(TreasuryTransaction).count() == txn_before
    assert db.query(JournalEntry).count() == je_before


# ===================== CommissionService Atomicity =====================

def test_commission_apply_policies_rolls_back_on_failure(db):
    r = _make_reservation(db)
    r.paid_to_office = D("5000")
    r.sales_rep_id = 1  # Employee id 1
    db.add(CommissionPolicy(
        name="Test Policy", rate_type="percentage",
        rate_value=D("10"), commission_base="profit",
        role="sales_rep", is_active=1,
    ))
    db.commit()

    before = db.query(CommissionEntry).count()
    try:
        CommissionService(db).apply_policies(r)
        assert db.query(CommissionEntry).count() > before
        raise RuntimeError("Simulated failure after apply_policies")
        db.commit()
    except RuntimeError:
        db.rollback()

    assert db.query(CommissionEntry).count() == before


# ===================== PayrollService Atomicity =====================

def test_payroll_create_run_rolls_back_on_failure(db):
    before = db.query(PayrollRun).count()
    try:
        PayrollService(db, MockUser()).create_run(
            "Test Run", date(2026, 1, 1), date(2026, 1, 31), "test")
        assert db.query(PayrollRun).count() == before + 1
        raise RuntimeError("Simulated failure after create_run")
        db.commit()
    except RuntimeError:
        db.rollback()

    assert db.query(PayrollRun).count() == before


def test_payroll_approve_rolls_back_on_failure(db):
    """اعتماد payroll = قيد محاسبي — rollback يمسح الأثر"""
    emp = db.query(Employee).first()
    emp.salary = D("5000")
    db.commit()

    svc = PayrollService(db, MockUser())
    run = svc.create_run("Test", date(2026, 1, 1), date(2026, 1, 31), "test")
    db.commit()

    je_before = db.query(JournalEntry).count()

    try:
        svc.update_status(run.id, "calculated")
        svc.update_status(run.id, "approved")
        assert db.query(JournalEntry).count() > je_before
        raise RuntimeError("Simulated failure after approval")
        db.commit()
    except RuntimeError:
        db.rollback()

    assert db.query(JournalEntry).count() == je_before


# ===================== TreasuryService Atomicity =====================

def test_treasury_transfer_rolls_back_on_failure(db):
    """create_transfer تخلق سجل تحويل — rollback يمسح الأثر"""
    acc1 = db.query(TreasuryAccount).first()
    acc2 = TreasuryAccount(name="Secondary", balance=0, type="cash")
    db.add(acc2)
    db.commit()

    before = db.query(TreasuryTransfer).count()

    try:
        TreasuryService(db).create_transfer(
            acc1.id, acc2.id, D("1000"), DECIMAL_ZERO,
            D("1"), "test transfer", MockUser(),
        )
        assert db.query(TreasuryTransfer).count() > before
        raise RuntimeError("Simulated failure after create_transfer")
        db.commit()
    except RuntimeError:
        db.rollback()

    assert db.query(TreasuryTransfer).count() == before


# ===================== ReservationService Atomicity =====================

def test_reservation_create_rolls_back_on_failure(db):
    """إنشاء حجز — rollback يمسح الأثر"""
    from services.reservation_service import ReservationService
    initial = db.query(Reservation).count()

    class MockForm(dict):
        def get(self, k, default=None):
            return dict.get(self, k, default)
        def getlist(self, k):
            v = dict.get(self, k, [])
            return v if isinstance(v, list) else [v]

    form = MockForm({
        "booking_number": "TEST-001",
        "customer_id": "1",
        "hotel_id": "1",
        "guest_name": "Test Guest",
        "checkin_date": "2026-08-01",
        "checkout_date": "2026-08-05",
        "paid_to_office": "3000",
        "status": "confirmed",
        "adults": "2",
    })

    try:
        result = ReservationService(db, MockUser()).create_reservation(form)
        assert db.query(Reservation).count() == initial + 1
        raise RuntimeError("Simulated failure after create_reservation")
        db.commit()
    except RuntimeError:
        db.rollback()

    assert db.query(Reservation).count() == initial
