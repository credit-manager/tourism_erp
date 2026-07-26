"""Accounting repository — Account, JournalEntry, JournalLine."""
from typing import Optional, List
from datetime import date
from sqlalchemy.orm import Session
from sqlalchemy import and_
from app.repositories.base import BaseRepository
from models import Account, JournalEntry, JournalLine


class AccountRepository(BaseRepository[Account]):
    def __init__(self, db: Session):
        super().__init__(Account, db)

    def find_by_code(self, code: str) -> Optional[Account]:
        return self.db.query(Account).filter(Account.code == code).first()

    def find_by_type(self, t: str) -> List[Account]:
        return self.db.query(Account).filter(Account.account_type == t).all()

    def chart_of_accounts(self) -> List[Account]:
        return self.db.query(Account).order_by(Account.code).all()


class JournalEntryRepository(BaseRepository[JournalEntry]):
    def __init__(self, db: Session):
        super().__init__(JournalEntry, db)

    def find_by_number(self, num: str) -> Optional[JournalEntry]:
        return self.db.query(JournalEntry).filter(JournalEntry.entry_number == num).first()

    def find_by_date_range(self, start: date, end: date) -> List[JournalEntry]:
        return self.db.query(JournalEntry).filter(
            and_(JournalEntry.date >= start, JournalEntry.date <= end)
        ).all()
