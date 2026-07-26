"""
Proves every journal entry is balanced (total debit == total credit).
Run: python -m pytest test_double_entry.py -v
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

import pytest
from decimal import Decimal
from datetime import date
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models import (
    Base, Account, JournalEntry, JournalLine, seed_chart_of_accounts,
    TreasuryAccount, Supplier, Customer, Currency,
)
from services.accounting_service import AccountingService, JournalImbalanceError
from currency_utils import D, DECIMAL_ZERO


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    seed_chart_of_accounts(session)
    # Seed treasury, supplier, customer for cache tests
    session.add(TreasuryAccount(name="Main Treasury", balance=0))
    session.add(Supplier(name="Test Supplier", balance=0))
    session.add(Customer(name="Test Customer", balance=0))
    session.commit()
    yield session
    session.close()


def test_balanced_entry_posts_successfully(db):
    svc = AccountingService(db)
    ar_id = svc._acc_id("ar")
    rev_id = svc._acc_id("sales_revenue")
    entry = svc.post(
        lines=[(ar_id, D("1000"), DECIMAL_ZERO), (rev_id, DECIMAL_ZERO, D("1000"))],
        source_type="manual", description="test",
    )
    assert entry.is_balanced
    assert entry.total_debit == D("1000")
    assert entry.total_credit == D("1000")


def test_unbalanced_entry_is_rejected(db):
    svc = AccountingService(db)
    ar_id = svc._acc_id("ar")
    rev_id = svc._acc_id("sales_revenue")
    with pytest.raises(JournalImbalanceError):
        svc.post(
            lines=[(ar_id, D("1000"), DECIMAL_ZERO), (rev_id, DECIMAL_ZERO, D("900"))],
            source_type="manual", description="broken",
        )
    assert db.query(JournalEntry).count() == 0


def test_zero_amount_entry_posts(db):
    svc = AccountingService(db)
    ar_id = svc._acc_id("ar")
    entry = svc.post(
        lines=[(ar_id, DECIMAL_ZERO, DECIMAL_ZERO)],
        source_type="manual", description="zero",
    )
    assert entry.is_balanced


def test_multiple_lines_balanced(db):
    svc = AccountingService(db)
    treasury_id = svc._acc_id("treasury")
    ar_id = svc._acc_id("ar")
    ap_id = svc._acc_id("ap")
    rev_id = svc._acc_id("sales_revenue")
    entry = svc.post(
        lines=[
            (treasury_id, D("5000"), DECIMAL_ZERO),
            (ar_id, DECIMAL_ZERO, D("3000")),
            (suspense_id := svc._acc_id("suspense"), DECIMAL_ZERO, D("2000")),
        ],
        source_type="manual", description="collection with suspense",
    )
    assert entry.is_balanced
    assert entry.total_debit == D("5000")
    assert entry.total_credit == D("5000")


def test_reservation_sale_and_cost(db):
    svc = AccountingService(db)
    # Manually create a mock reservation
    class MockReservation:
        id = 1
        booking_number = "BK-2026-000001"
        guest_name = "Test Guest"
        created_date = date.today()
        net_sale_price = D("5000")
        company_cost = D("5000")
        stay_cost = D("3000")
        paid_to_office = DECIMAL_ZERO
        remaining_to_office = D("5000")
        remaining_to_hotel = D("3000")

    reservation = MockReservation()
    svc.post_reservation_sale(reservation)
    svc.post_reservation_cost(reservation)

    entries = db.query(JournalEntry).all()
    assert len(entries) == 2
    for e in entries:
        assert e.is_balanced

    # Sale entry: Dr AR / Cr Revenue = 5000
    sale_entry = next(e for e in entries if "إيراد" in e.description)
    assert sale_entry.total_debit == D("5000")
    assert sale_entry.total_credit == D("5000")

    # Cost entry: Dr COGS / Cr AP = 3000
    cost_entry = next(e for e in entries if "تكلفة" in e.description)
    assert cost_entry.total_debit == D("3000")
    assert cost_entry.total_credit == D("3000")


def test_collection_fully_allocated(db):
    svc = AccountingService(db)
    class MockCollection:
        id = 1
        collection_number = "COL-2026-000001"
        payer_name = "Test Payer"
        date = date.today()
        allocated_amount = D("5000")
        unallocated_amount = DECIMAL_ZERO

    class MockReservation:
        id = 1
        booking_number = "BK-2026-000001"

    collection = MockCollection()
    svc.post_collection(collection, D("5000"))

    entries = db.query(JournalEntry).all()
    assert len(entries) == 1
    entry = entries[0]
    assert entry.is_balanced
    assert entry.total_debit == D("5000")
    assert entry.total_credit == D("5000")

    # Verify Dr Treasury 5000, Cr AR 5000
    lines = entry.lines
    treasury_line = next(l for l in lines if l.account_id == svc._acc_id("treasury"))
    ar_line = next(l for l in lines if l.account_id == svc._acc_id("ar"))
    assert treasury_line.debit == D("5000")
    assert ar_line.credit == D("5000")


def test_collection_with_unallocated_suspense(db):
    svc = AccountingService(db)
    class MockCollection:
        id = 1
        collection_number = "COL-2026-000002"
        payer_name = "Partial Payer"
        date = date.today()
        allocated_amount = D("3000")
        unallocated_amount = D("2000")

    collection = MockCollection()
    svc.post_collection(collection, D("5000"))

    entry = db.query(JournalEntry).first()
    assert entry.is_balanced
    assert entry.total_debit == D("5000")
    assert entry.total_credit == D("5000")

    # Dr Treasury 5000, Cr AR 3000, Cr Suspense 2000
    lines = entry.lines
    treasury_line = next(l for l in lines if l.account_id == svc._acc_id("treasury"))
    ar_line = next(l for l in lines if l.account_id == svc._acc_id("ar"))
    suspense_line = next(l for l in lines if l.account_id == svc._acc_id("suspense"))
    assert treasury_line.debit == D("5000")
    assert ar_line.credit == D("3000")
    assert suspense_line.credit == D("2000")


def test_supplier_payment(db):
    svc = AccountingService(db)
    class MockSupplier:
        name = "Test Supplier"

    class MockPayment:
        id = 1
        payment_number = "SPAY-2026-000001"
        date = date.today()
        allocated_amount = D("3000")
        unallocated_amount = DECIMAL_ZERO
        supplier = MockSupplier()

    payment = MockPayment()
    svc.post_supplier_payment(payment, D("3000"))

    entry = db.query(JournalEntry).first()
    assert entry.is_balanced
    # Dr AP 3000, Cr Treasury 3000
    ap_line = next(l for l in entry.lines if l.account_id == svc._acc_id("ap"))
    treasury_line = next(l for l in entry.lines if l.account_id == svc._acc_id("treasury"))
    assert ap_line.debit == D("3000")
    assert treasury_line.credit == D("3000")


def test_expense_posting(db):
    svc = AccountingService(db)
    class MockExpense:
        id = 1
        amount = D("500")
        description = "كهرباء"
        category = "مرافق"
        date = date.today()

    expense = MockExpense()
    svc.post_expense(expense)

    entry = db.query(JournalEntry).first()
    assert entry.is_balanced
    assert entry.total_debit == D("500")
    assert entry.total_credit == D("500")


def test_withdrawal_posting(db):
    svc = AccountingService(db)
    class MockEmployee:
        name = "Ahmed"

    class MockWithdrawal:
        id = 1
        amount = D("1000")
        withdrawal_type = "salary"
        date = date.today()
        employee = MockEmployee()

    withdrawal = MockWithdrawal()
    svc.post_withdrawal(withdrawal)

    entry = db.query(JournalEntry).first()
    assert entry.is_balanced
    assert entry.total_debit == D("1000")
    assert entry.total_credit == D("1000")


def test_commission_posting(db):
    svc = AccountingService(db)
    class MockReservation:
        id = 1
        booking_number = "BK-2026-000002"
        created_date = date.today()

    reservation = MockReservation()
    svc.post_commission(reservation, D("200"), "reservation_rep", "Ahmed")

    entry = db.query(JournalEntry).first()
    assert entry.is_balanced
    assert entry.total_debit == D("200")
    assert entry.total_credit == D("200")
    comm_line = next(l for l in entry.lines if l.account_id == svc._acc_id("commissions"))
    ap_line = next(l for l in entry.lines if l.account_id == svc._acc_id("ap"))
    assert comm_line.debit == D("200")
    assert ap_line.credit == D("200")


def test_balance_computation(db):
    svc = AccountingService(db)
    # Post two entries
    svc.post(
        lines=[(svc._acc_id("treasury"), D("1000"), DECIMAL_ZERO),
               (svc._acc_id("ar"), DECIMAL_ZERO, D("1000"))],
        source_type="manual", description="entry 1",
    )
    svc.post(
        lines=[(svc._acc_id("ar"), D("500"), DECIMAL_ZERO),
               (svc._acc_id("treasury"), DECIMAL_ZERO, D("500"))],
        source_type="manual", description="entry 2",
    )
    # Treasury balance = 1000 - 500 = 500
    assert svc.get_balance(svc._acc_id("treasury")) == D("500")
    # AR balance = -1000 + 500 = -500 (credit balance)
    assert svc.get_balance(svc._acc_id("ar")) == D("-500")


def test_reverse_entry(db):
    svc = AccountingService(db)
    original = svc.post(
        lines=[(svc._acc_id("treasury"), D("1000"), DECIMAL_ZERO),
               (svc._acc_id("ar"), DECIMAL_ZERO, D("1000"))],
        source_type="manual", description="original",
    )
    reversal = svc.reverse_entry(original.id)
    assert reversal.is_reversal == 1
    assert reversal.reversed_entry_id == original.id
    assert reversal.is_balanced
    # Reversal swaps debit/credit
    rev_treasury = next(l for l in reversal.lines if l.account_id == svc._acc_id("treasury"))
    rev_ar = next(l for l in reversal.lines if l.account_id == svc._acc_id("ar"))
    assert rev_treasury.credit == D("1000")  # was debit, now credit
    assert rev_ar.debit == D("1000")         # was credit, now debit
    # After reversal, balance should be 0
    assert svc.get_balance(svc._acc_id("treasury")) == D("0")


def test_get_balance_as_of(db):
    svc = AccountingService(db)
    svc.post(
        lines=[(svc._acc_id("treasury"), D("1000"), DECIMAL_ZERO),
               (svc._acc_id("ar"), DECIMAL_ZERO, D("1000"))],
        source_type="manual", description="entry 1",
        entry_date=date(2026, 1, 15),
    )
    svc.post(
        lines=[(svc._acc_id("treasury"), D("500"), DECIMAL_ZERO),
               (svc._acc_id("ar"), DECIMAL_ZERO, D("500"))],
        source_type="manual", description="entry 2",
        entry_date=date(2026, 2, 1),
    )
    # As of Jan 31: only first entry
    assert svc.get_balance(svc._acc_id("treasury"), as_of=date(2026, 1, 31)) == D("1000")
    # As of Feb 28: both entries
    assert svc.get_balance(svc._acc_id("treasury"), as_of=date(2026, 2, 28)) == D("1500")


# -------- Cached balance tests --------
def test_post_updates_treasury_cache(db):
    """After posting, TreasuryAccount.balance should match journal-derived total."""
    svc = AccountingService(db)
    svc.post(
        lines=[(svc._acc_id("treasury"), D("5000"), DECIMAL_ZERO),
               (svc._acc_id("ar"), DECIMAL_ZERO, D("5000"))],
        source_type="manual", description="collection",
    )
    total = D(db.query(TreasuryAccount).first().balance)
    assert total == D("5000"), f"Expected 5000, got {total}"


def test_verify_all_no_discrepancies_when_clean(db):
    """After posting, verify_all() should return empty list."""
    svc = AccountingService(db)
    svc.post(
        lines=[(svc._acc_id("treasury"), D("3000"), DECIMAL_ZERO),
               (svc._acc_id("ar"), DECIMAL_ZERO, D("3000"))],
        source_type="manual", description="clean entry",
    )
    discrepancies = svc.verify_all()
    assert discrepancies == [], f"Expected no discrepancies, got {discrepancies}"


def test_verify_all_detects_direct_cache_modification(db):
    """Directly modifying TreasuryAccount.balance creates a detectable discrepancy."""
    svc = AccountingService(db)
    svc.post(
        lines=[(svc._acc_id("treasury"), D("1000"), DECIMAL_ZERO),
               (svc._acc_id("ar"), DECIMAL_ZERO, D("1000"))],
        source_type="manual", description="entry",
    )
    treasury = db.query(TreasuryAccount).first()
    treasury.balance = D("9999")  # Direct modification - should NOT happen in real code
    db.flush()
    discrepancies = svc.verify_all()
    assert len(discrepancies) >= 1, "Should detect treasury discrepancy"
    assert any(d["entity"] == "TreasuryAccount" for d in discrepancies), (
        f"Expected TreasuryAccount issue, got {discrepancies}"
    )


def test_sync_all_caches_fixes_discrepancies(db):
    """sync_all_caches() should correct any manually broken cached balances."""
    svc = AccountingService(db)
    svc.post(
        lines=[(svc._acc_id("treasury"), D("2000"), DECIMAL_ZERO),
               (svc._acc_id("ar"), DECIMAL_ZERO, D("2000"))],
        source_type="manual", description="entry",
    )
    treasury = db.query(TreasuryAccount).first()
    treasury.balance = D("0")  # break it
    db.flush()
    assert len(svc.verify_all()) >= 1
    svc.sync_all_caches()
    db.flush()
    discrepancies = svc.verify_all()
    assert discrepancies == [], f"sync_all_caches should fix, got {discrepancies}"
    assert D(db.query(TreasuryAccount).first().balance) == D("2000"), "Treasury balance should be 2000 after sync"


def test_supplier_cache_updates_on_ap_journal(db):
    """Posting an AP entry with supplier_id should update Supplier.balance."""
    from models import JournalLine
    svc = AccountingService(db)
    ap_id = svc._acc_id("ap")
    supplier = db.query(Supplier).first()
    entry = svc.post(
        lines=[(svc._acc_id("cogs_hotels"), D("1500"), DECIMAL_ZERO),
               (ap_id, DECIMAL_ZERO, D("1500"))],
        source_type="manual", description="cost",
    )
    # Manually set supplier_id on the AP journal line (the test creates lines without one)
    line = db.query(JournalLine).filter(
        JournalLine.entry_id == entry.id, JournalLine.account_id == ap_id
    ).first()
    line.supplier_id = supplier.id
    db.flush()
    svc.sync_all_caches()
    expected = D(db.query(Supplier).first().balance)
    assert expected == D("1500"), f"Supplier balance should be 1500, got {expected}"


def test_customer_cache_updates_on_ar_journal(db):
    """Posting an AR entry with customer_id should update Customer.balance."""
    from models import JournalLine
    svc = AccountingService(db)
    ar_id = svc._acc_id("ar")
    customer = db.query(Customer).first()
    entry = svc.post(
        lines=[(ar_id, D("2500"), DECIMAL_ZERO),
               (svc._acc_id("sales_revenue"), DECIMAL_ZERO, D("2500"))],
        source_type="manual", description="sale",
    )
    line = db.query(JournalLine).filter(
        JournalLine.entry_id == entry.id, JournalLine.account_id == ar_id
    ).first()
    line.customer_id = customer.id
    db.flush()
    svc.sync_all_caches()
    expected = D(db.query(Customer).first().balance)
    assert expected == D("2500"), f"Customer balance should be 2500, got {expected}"


def test_manual_cache_modification_causes_discrepancy(db):
    """Directly modifying Supplier.balance should be detected by verify_all()."""
    svc = AccountingService(db)
    supplier = db.query(Supplier).first()
    supplier.balance = D("5000")  # Direct modification without journal entry
    db.flush()
    discrepancies = svc.verify_all()
    assert any(d["entity"] == "Supplier" and d["id"] == supplier.id for d in discrepancies), (
        "Should detect supplier with balance but no journal entries"
    )


# -------- Reservation modification / adjustment tests --------
def test_adjust_reservation_reverses_and_reposts(db):
    """adjust_reservation reverses old entries and posts new ones after financial change."""
    from models import Reservation
    svc = AccountingService(db)
    res = Reservation(
        booking_number="ADJ-TEST-1", guest_name="Test", company_cost=D("1000"),
        stay_cost=D("600"), discount=DECIMAL_ZERO, taxes=DECIMAL_ZERO,
    )
    db.add(res)
    db.flush()
    svc.post_reservation_sale(res)
    svc.post_reservation_cost(res)
    # Change financial values
    res.company_cost = D("1500")
    res.stay_cost = D("800")
    db.flush()
    old_snap = {"net_sale_price": "1000", "stay_cost": "600",
                "employee_commission": "0", "travel_agent_commission_amount": "0",
                "sales_rep_commission_amount": "0", "marketing_rep_commission_amount": "0",
                "ops_supplier_commission_amount": "0"}
    svc.adjust_reservation(res, old_snap)
    ar_bal = svc.get_balance(svc._acc_id("ar"))
    assert ar_bal == D("1500"), f"Expected AR 1500 after adjustment, got {ar_bal}"
    ap_bal = svc.get_balance(svc._acc_id("ap"))
    # AP is credit-normal (liability), so get_balance returns negative
    assert ap_bal == D("-800"), f"Expected AP -800 after adjustment, got {ap_bal}"


def test_adjust_reservation_noop_when_no_old_entries(db):
    """adjust_reservation does nothing if reservation has no accounting entries yet."""
    from models import Reservation
    svc = AccountingService(db)
    res = Reservation(booking_number="ADJ-TEST-2", guest_name="Test",
                      company_cost=D("1000"), stay_cost=D("600"),
                      discount=DECIMAL_ZERO, taxes=DECIMAL_ZERO)
    db.add(res)
    db.flush()
    old_snap = {"net_sale_price": "1000", "stay_cost": "600",
                "employee_commission": "0", "travel_agent_commission_amount": "0",
                "sales_rep_commission_amount": "0", "marketing_rep_commission_amount": "0",
                "ops_supplier_commission_amount": "0"}
    svc.adjust_reservation(res, old_snap)
    assert db.query(JournalEntry).count() == 0, "No entries should be created"


def test_modify_without_financial_change_does_not_create_entries(db):
    """ReservationService.modify with only non-financial changes skips accounting."""
    from models import Reservation
    from services.reservation_service import ReservationService
    res = Reservation(booking_number="ADJ-TEST-3", guest_name="Old Name",
                      company_cost=D("1000"), stay_cost=D("600"),
                      discount=DECIMAL_ZERO, taxes=DECIMAL_ZERO)
    db.add(res)
    db.flush()
    svc = AccountingService(db)
    svc.post_reservation_sale(res)
    svc.post_reservation_cost(res)
    before = db.query(JournalEntry).count()
    # "Modify" — change only guest_name, pass all financial fields unchanged
    class MockUser: username = "test"; role = "admin"
    rsvc = ReservationService(db, MockUser())
    rsvc.modify(res.id, {"guest_name": "New Name", "company_cost": "1000",
                          "stay_cost": "600", "discount": "0", "taxes": "0",
                          "paid_to_office": "0", "paid_to_hotel": "0",
                          "transportation_cost": "0", "excursions_cost": "0",
                          "visa_cost": "0", "insurance_cost": "0",
                          "other_services_cost": "0",
                          "reservation_rep_commission_type": "percentage",
                          "reservation_rep_commission_value": "0",
                          "travel_agent_commission_type": "percentage",
                          "travel_agent_commission_value": "0",
                          "sales_rep_commission_type": "percentage",
                          "sales_rep_commission_value": "0",
                          "marketing_rep_commission_type": "percentage",
                          "marketing_rep_commission_value": "0",
                          "ops_supplier_commission_type": "percentage",
                          "ops_supplier_commission_value": "0",
                          "customer_id": "", "hotel_id": "", "ops_supplier_id": "",
                          "employee_id": "", "travel_agent_id": "",
                          "sales_rep_id": "", "marketing_rep_id": "",
                          "service_ids": []},
                reason="rename")
    after = db.query(JournalEntry).count()
    assert after == before, "No new journal entries expected for non-financial change"
    assert db.query(Reservation).get(res.id).guest_name == "New Name"


def test_modify_with_financial_change_creates_adjustment(db):
    """ReservationService.modify with financial change reverses old and posts new entries."""
    from models import Reservation, AuditLog
    from services.reservation_service import ReservationService
    import json
    res = Reservation(booking_number="ADJ-TEST-4", guest_name="Test Guest",
                      company_cost=D("2000"), stay_cost=D("1200"),
                      discount=DECIMAL_ZERO, taxes=DECIMAL_ZERO)
    db.add(res)
    db.flush()
    svc = AccountingService(db)
    svc.post_reservation_sale(res)
    svc.post_reservation_cost(res)
    # Modify via service — change company_cost only
    class MockUser: username = "test"; role = "admin"
    rsvc = ReservationService(db, MockUser())
    diffs = rsvc.modify(res.id, {"guest_name": "Test Guest", "company_cost": "2500",
                                  "stay_cost": "1200", "discount": "0", "taxes": "0",
                                  "paid_to_office": "0", "paid_to_hotel": "0",
                                  "transportation_cost": "0", "excursions_cost": "0",
                                  "visa_cost": "0", "insurance_cost": "0",
                                  "other_services_cost": "0",
                                  "reservation_rep_commission_type": "percentage",
                                  "reservation_rep_commission_value": "0",
                                  "travel_agent_commission_type": "percentage",
                                  "travel_agent_commission_value": "0",
                                  "sales_rep_commission_type": "percentage",
                                  "sales_rep_commission_value": "0",
                                  "marketing_rep_commission_type": "percentage",
                                  "marketing_rep_commission_value": "0",
                                  "ops_supplier_commission_type": "percentage",
                                  "ops_supplier_commission_value": "0",
                                  "customer_id": "", "hotel_id": "", "ops_supplier_id": "",
                                  "employee_id": "", "travel_agent_id": "",
                                  "sales_rep_id": "", "marketing_rep_id": "",
                                  "service_ids": []},
                        reason="تعديل سعر البيع")
    assert "net_sale_price" in diffs, f"Expected net_sale_price diff, got {diffs}"
    ar_bal = svc.get_balance(svc._acc_id("ar"))
    assert ar_bal == D("2500"), f"Expected AR 2500 after modification, got {ar_bal}"
    # Audit log
    logs = db.query(AuditLog).filter(
        AuditLog.table_name == "reservations",
        AuditLog.record_id == res.id,
        AuditLog.action == "adjustment",
    ).all()
    assert len(logs) >= 1, "Expected at least one audit log for the adjustment"
    log = logs[-1]
    old_vals = json.loads(log.old_values)
    new_vals = json.loads(log.new_values)
    assert old_vals.get("net_sale_price") == "2000.00", f"Expected old 2000.00, got {old_vals}"
    assert new_vals.get("net_sale_price") == "2500.00", f"Expected new 2500.00, got {new_vals}"
    assert log.reason == "تعديل سعر البيع"


# -------- Cancellation tests --------
def test_cancel_reservation_reverses_accounting(db):
    """Cancel reservation reverses sale + cost entries and clears AR/AP."""
    from models import Reservation
    svc = AccountingService(db)
    res = Reservation(booking_number="CAN-TEST-1", guest_name="Test",
                      company_cost=D("1000"), stay_cost=D("600"),
                      discount=DECIMAL_ZERO, taxes=DECIMAL_ZERO)
    db.add(res)
    db.flush()
    svc.post_reservation_sale(res)
    svc.post_reservation_cost(res)
    ar_before = svc.get_balance(svc._acc_id("ar"))
    ap_before = svc.get_balance(svc._acc_id("ap"))
    assert ar_before == D("1000")
    assert ap_before == D("-600")
    # Cancel
    from services.reservation_service import ReservationService
    class MockUser: username = "canceller"; role = "admin"
    rsvc = ReservationService(db, MockUser())
    rsvc.cancel(res.id, reason="test cancel")
    db.flush()
    ar_after = svc.get_balance(svc._acc_id("ar"))
    ap_after = svc.get_balance(svc._acc_id("ap"))
    assert ar_after == DECIMAL_ZERO, f"Expected AR 0 after cancel, got {ar_after}"
    assert ap_after == DECIMAL_ZERO, f"Expected AP 0 after cancel, got {ap_after}"
    assert db.query(Reservation).get(res.id).status == "cancelled"


def test_cancel_reservation_with_refund_and_fee(db):
    """Cancel with refund + cancellation fee posts additional adjustment entries."""
    from models import Reservation
    svc = AccountingService(db)
    res = Reservation(booking_number="CAN-TEST-2", guest_name="Test",
                      company_cost=D("2000"), stay_cost=D("1200"),
                      discount=DECIMAL_ZERO, taxes=DECIMAL_ZERO)
    db.add(res)
    db.flush()
    svc.post_reservation_sale(res)
    # Cancel with 500 refund + 100 fee
    from services.reservation_service import ReservationService
    class MockUser: username = "admin"; role = "admin"
    rsvc = ReservationService(db, MockUser())
    rsvc.cancel(res.id, reason="customer request",
                refund_amount=D("500"), cancellation_fee=D("100"))
    db.flush()
    ar_bal = svc.get_balance(svc._acc_id("ar"))
    assert ar_bal == DECIMAL_ZERO, f"Expected AR 0, got {ar_bal}"
    # Revenue should reflect reversal (original 2000) + fee (100) = -100 + 1900 = ...
    # Actually: original Cr 2000 → reverse Dr 2000 → fee Cr 100 → net = -1900
    # get_balance = debit - credit = 2000 - 2100 = -100
    rev_bal = svc.get_balance(svc._acc_id("sales_revenue"))
    assert rev_bal == D("-100"), f"Expected Revenue -100 (2000 reversed + 100 fee), got {rev_bal}"


def test_cancel_draft_without_accounting(db):
    """Cancel a draft reservation (no accounting entries) sets status without errors."""
    from models import Reservation
    from services.reservation_service import ReservationService
    res = Reservation(booking_number="CAN-TEST-3", guest_name="Draft",
                      status="draft", company_cost=DECIMAL_ZERO, stay_cost=DECIMAL_ZERO,
                      discount=DECIMAL_ZERO, taxes=DECIMAL_ZERO)
    db.add(res)
    db.flush()
    class MockUser: username = "admin"; role = "admin"
    rsvc = ReservationService(db, MockUser())
    rsvc.cancel(res.id, reason="not needed")
    db.flush()
    assert db.query(Reservation).get(res.id).status == "cancelled"
    assert db.query(Reservation).get(res.id).cancellation_reason == "not needed"


def test_hard_delete_draft_without_docs(db):
    """Hard-delete a draft with no docs/entries succeeds."""
    from models import Reservation
    from services.reservation_service import ReservationService
    res = Reservation(booking_number="DEL-TEST-1", guest_name="Draft",
                      status="draft", company_cost=DECIMAL_ZERO, stay_cost=DECIMAL_ZERO,
                      discount=DECIMAL_ZERO, taxes=DECIMAL_ZERO)
    db.add(res)
    db.flush()
    rid = res.id
    class MockUser: username = "admin"; role = "admin"
    ReservationService(db, MockUser()).hard_delete(rid)
    db.flush()
    assert db.query(Reservation).get(rid) is None, "Draft should be hard-deleted"


def test_hard_delete_rejects_confirmed(db):
    """Hard-delete should reject a non-draft reservation."""
    from models import Reservation
    from services.reservation_service import ReservationService
    res = Reservation(booking_number="DEL-TEST-2", guest_name="Confirmed",
                      status="confirmed", company_cost=D("500"), stay_cost=D("300"),
                      discount=DECIMAL_ZERO, taxes=DECIMAL_ZERO)
    db.add(res)
    db.flush()
    class MockUser: username = "admin"; role = "admin"
    import pytest
    with pytest.raises(ValueError, match="للمسودات"):
        ReservationService(db, MockUser()).hard_delete(res.id)
