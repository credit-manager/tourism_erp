"""Reservation repository — encapsulates all reservation/booking DB queries."""
from typing import Optional, List
from datetime import date, datetime
from sqlalchemy.orm import Session
from sqlalchemy import and_
from app.repositories.base import BaseRepository
from models import Reservation, Booking


class ReservationRepository(BaseRepository[Reservation]):
    def __init__(self, db: Session):
        super().__init__(Reservation, db)

    def find_by_booking_number(self, num: str) -> Optional[Reservation]:
        return self.db.query(Reservation).filter(Reservation.booking_number == num).first()

    def find_by_customer(self, customer_id: int) -> List[Reservation]:
        return self.db.query(Reservation).filter(Reservation.customer_id == customer_id).all()

    def find_by_hotel(self, hotel_id: int) -> List[Reservation]:
        return self.db.query(Reservation).filter(Reservation.hotel_id == hotel_id).all()

    def find_by_employee(self, employee_id: int) -> List[Reservation]:
        return self.db.query(Reservation).filter(
            (Reservation.employee_id == employee_id) |
            (Reservation.sales_rep_id == employee_id) |
            (Reservation.marketing_rep_id == employee_id)
        ).all()

    def find_by_date_range(self, start: date, end: date) -> List[Reservation]:
        return self.db.query(Reservation).filter(
            and_(Reservation.checkin_date >= start, Reservation.checkin_date <= end)
        ).all()

    def find_by_status(self, status: str) -> List[Reservation]:
        return self.db.query(Reservation).filter(Reservation.status == status).all()

    def find_active(self) -> List[Reservation]:
        return self.db.query(Reservation).filter(
            Reservation.status.in_(["confirmed", "checked_in"])
        ).all()
