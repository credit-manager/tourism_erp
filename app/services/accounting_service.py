"""Service layer: accounting/ledger business logic."""
from typing import List, Optional
from datetime import date
from decimal import Decimal
from sqlalchemy.orm import Session
from app.repositories.accounting_repository import AccountRepository, JournalEntryRepository
from models import Account, JournalEntry, JournalLine


class AccountingService:
    def __init__(self, db: Session):
        self.accounts = AccountRepository(db)
        self.entries = JournalEntryRepository(db)

    def chart_of_accounts(self) -> List[Account]:
        return self.accounts.chart_of_accounts()

    def get_account(self, aid: int) -> Optional[Account]:
        return self.accounts.get(aid)

    def find_by_code(self, code: str) -> Optional[Account]:
        return self.accounts.find_by_code(code)
