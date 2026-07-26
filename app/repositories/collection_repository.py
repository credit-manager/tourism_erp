"""Collection repository."""
from typing import List
from datetime import date
from sqlalchemy.orm import Session
from sqlalchemy import and_
from app.repositories.base import BaseRepository
from models import Collection


class CollectionRepository(BaseRepository[Collection]):
    def __init__(self, db: Session):
        super().__init__(Collection, db)

    def find_by_customer(self, customer_id: int) -> List[Collection]:
        return self.db.query(Collection).filter(Collection.customer_id == customer_id).all()

    def find_by_date_range(self, start: date, end: date) -> List[Collection]:
        return self.db.query(Collection).filter(
            and_(Collection.date >= start, Collection.date <= end)
        ).all()

    def find_unallocated(self) -> List[Collection]:
        return self.db.query(Collection).filter(Collection.allocated_amount < Collection.total_amount).all()
