"""Service layer: collection business logic."""
from typing import List, Optional
from datetime import date
from sqlalchemy.orm import Session
from app.repositories.collection_repository import CollectionRepository
from models import Collection


class CollectionService:
    def __init__(self, db: Session):
        self.repo = CollectionRepository(db)

    def get(self, cid: int) -> Optional[Collection]:
        return self.repo.get(cid)

    def list_by_customer(self, customer_id: int) -> List[Collection]:
        return self.repo.find_by_customer(customer_id)

    def list_unallocated(self) -> List[Collection]:
        return self.repo.find_unallocated()
