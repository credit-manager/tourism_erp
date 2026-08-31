from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.services.ledger_service import LedgerService, _money
from app.core.exceptions import JournalImbalanceError


def _service():
    db = MagicMock()
    db.query.return_value.filter.return_value.scalar.return_value = None
    db.query.return_value.filter.return_value.first.return_value = None
    db.flush.return_value = None
    return LedgerService(db), db


def test_money_avoids_binary_float_rounding():
    assert _money(10.005) == Decimal("10.01")
    assert _money("10.004") == Decimal("10.00")


def test_post_rejects_empty_entry():
    service, _ = _service()
    with pytest.raises(JournalImbalanceError):
        service.post([], "test", 1)


def test_post_rejects_negative_amount():
    service, _ = _service()
    with pytest.raises(JournalImbalanceError):
        service.post([(1, -1, 0), (2, 0, 1)], "test", 1)


def test_post_rejects_line_with_both_sides():
    service, _ = _service()
    with pytest.raises(JournalImbalanceError):
        service.post([(1, 5, 5)], "test", 1)


def test_post_rejects_unbalanced_entry():
    service, _ = _service()
    with pytest.raises(JournalImbalanceError):
        service.post([(1, 100, 0), (2, 0, 99)], "test", 1)


def test_post_preserves_every_normalized_line():
    service, db = _service()
    entry = service.post([(1, 100, 0), (2, 0, 100)], "test", 1)
    assert entry.entry_number == "JE-" + str(date.today().year) + "-00001"
    assert db.add.call_count == 3  # entry + two journal lines
    added_lines = [call.args[0] for call in db.add.call_args_list[1:]]
    assert [(x.account_id, x.debit, x.credit) for x in added_lines] == [
        (1, Decimal("100.00"), Decimal("0.00")),
        (2, Decimal("0.00"), Decimal("100.00")),
    ]


def test_reverse_entry_swaps_debit_and_credit_and_preserves_dimensions():
    service, db = _service()
    original_line = SimpleNamespace(
        id=10,
        account_id=7,
        debit=Decimal("100.00"),
        credit=Decimal("0.00"),
        currency_id=2,
        exchange_rate=Decimal("30.5"),
        amount_in_base_currency=Decimal("3050.00"),
        cost_center="OPS",
        branch="CAI",
        customer_id=4,
        supplier_id=None,
        reservation_id=9,
    )
    original = SimpleNamespace(
        id=20,
        entry_number="JE-2026-00020",
        is_reversal=0,
        lines=[original_line],
        reversals=[],
    )
    db.get.return_value = original
    reversal = service.reverse_entry(20, "tester", "Cancellation")
    assert reversal.reversed_entry_id == 20
    assert reversal.is_reversal == 1
    added_line = db.add.call_args_list[-1].args[0]
    assert added_line.debit == Decimal("0.00")
    assert added_line.credit == Decimal("100.00")
    assert added_line.currency_id == 2
    assert added_line.reservation_id == 9
