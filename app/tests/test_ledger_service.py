"""
Proves the structural guarantee: you cannot post an unbalanced journal entry.
Run: python -m pytest app/tests/test_ledger_service.py -v
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.models.accounting import Account, JournalEntry, JournalLine
from app.services.ledger_service import LedgerService
from app.core.exceptions import JournalImbalanceError


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    treasury = Account(code="1000", name="Treasury", account_type="asset", normal_side="debit")
    revenue = Account(code="4000", name="Sales Revenue", account_type="revenue", normal_side="credit")
    session.add_all([treasury, revenue])
    session.commit()
    yield session, treasury.id, revenue.id
    session.close()


def test_balanced_entry_posts_successfully(db):
    session, treasury_id, revenue_id = db
    ledger = LedgerService(session)
    entry = ledger.post(
        lines=[(treasury_id, 1000, 0), (revenue_id, 0, 1000)],
        source_type="manual", description="test sale",
    )
    assert entry.is_balanced
    assert ledger.get_balance(treasury_id) == 1000
    assert ledger.get_balance(revenue_id) == 1000


def test_unbalanced_entry_is_rejected(db):
    session, treasury_id, revenue_id = db
    ledger = LedgerService(session)
    with pytest.raises(JournalImbalanceError):
        ledger.post(
            lines=[(treasury_id, 1000, 0), (revenue_id, 0, 900)],   # mismatched on purpose
            source_type="manual", description="broken entry",
        )
    # and no entry should have been persisted
    assert session.query(JournalEntry).count() == 0
