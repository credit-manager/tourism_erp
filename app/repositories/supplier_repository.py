"""Supplier repository."""
from typing import Optional, List
from sqlalchemy.orm import Session
from app.repositories.base import BaseRepository
from models import Supplier, SupplierConfirmation, SupplierInvoice


class SupplierRepository(BaseRepository[Supplier]):
    def __init__(self, db: Session):
        super().__init__(Supplier, db)

    def search(self, q: str) -> List[Supplier]:
        pat = f"%{q}%"
        return self.db.query(Supplier).filter(Supplier.name.ilike(pat)).all()


class SupplierConfirmationRepository(BaseRepository[SupplierConfirmation]):
    def __init__(self, db: Session):
        super().__init__(SupplierConfirmation, db)


class SupplierInvoiceRepository(BaseRepository[SupplierInvoice]):
    def __init__(self, db: Session):
        super().__init__(SupplierInvoice, db)
