"""Service layer: reservation/booking business logic."""
from typing import List, Optional
from decimal import Decimal
from sqlalchemy.orm import Session
from app.repositories.reservation_repository import ReservationRepository
from models import Reservation, Booking


class ReservationService:
    def __init__(self, db: Session):
        self.repo = ReservationRepository(db)

    def get(self, rid: int) -> Optional[Reservation]:
        return self.repo.get(rid)

    def list_by_customer(self, customer_id: int) -> List[Reservation]:
        return self.repo.find_by_customer(customer_id)

    def list_by_status(self, status: str) -> List[Reservation]:
        return self.repo.find_by_status(status)

    def list_active(self) -> List[Reservation]:
        return self.repo.find_active()
