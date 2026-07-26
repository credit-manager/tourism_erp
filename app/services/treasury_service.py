"""Service layer: treasury/financial business logic."""
from typing import List, Optional
from sqlalchemy.orm import Session
from app.repositories.treasury_repository import TreasuryAccountRepository, TreasuryTransactionRepository
from models import TreasuryAccount, TreasuryTransaction


class TreasuryService:
    def __init__(self, db: Session):
        self.accounts = TreasuryAccountRepository(db)
        self.transactions = TreasuryTransactionRepository(db)

    def get_account_balance(self, account_id: int) -> Optional[TreasuryAccount]:
        return self.accounts.get(account_id)
