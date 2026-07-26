"""Treasury repository."""
from typing import Optional, List
from datetime import date, datetime
from sqlalchemy.orm import Session
from sqlalchemy import and_
from app.repositories.base import BaseRepository
from models import TreasuryAccount, TreasuryTransaction, Expense


class TreasuryAccountRepository(BaseRepository[TreasuryAccount]):
    def __init__(self, db: Session):
        super().__init__(TreasuryAccount, db)

    def find_by_type(self, t: str) -> List[TreasuryAccount]:
        return self.db.query(TreasuryAccount).filter(TreasuryAccount.account_type == t).all()

    def find_active(self) -> List[TreasuryAccount]:
        return self.db.query(TreasuryAccount).filter(TreasuryAccount.is_active == 1).all()


class TreasuryTransactionRepository(BaseRepository[TreasuryTransaction]):
    def __init__(self, db: Session):
        super().__init__(TreasuryTransaction, db)

    def find_by_account(self, account_id: int) -> List[TreasuryTransaction]:
        return self.db.query(TreasuryTransaction).filter(
            (TreasuryTransaction.from_account_id == account_id) |
            (TreasuryTransaction.to_account_id == account_id)
        ).order_by(TreasuryTransaction.created_at.desc()).all()

    def find_by_date_range(self, start: date, end: date) -> List[TreasuryTransaction]:
        return self.db.query(TreasuryTransaction).filter(
            and_(TreasuryTransaction.created_at >= start, TreasuryTransaction.created_at <= end)
        ).all()

    def find_by_reference(self, ref: str) -> Optional[TreasuryTransaction]:
        return self.db.query(TreasuryTransaction).filter(TreasuryTransaction.reference == ref).first()
