"""Hotel repository."""
from typing import Optional, List
from sqlalchemy.orm import Session
from app.repositories.base import BaseRepository
from models import Hotel, RoomType, PriceSeason


class HotelRepository(BaseRepository[Hotel]):
    def __init__(self, db: Session):
        super().__init__(Hotel, db)

    def search(self, q: str) -> List[Hotel]:
        pat = f"%{q}%"
        return self.db.query(Hotel).filter(Hotel.name.ilike(pat)).all()

    def find_active(self) -> List[Hotel]:
        return self.db.query(Hotel).filter(Hotel.is_active == 1).all()


class RoomTypeRepository(BaseRepository[RoomType]):
    def __init__(self, db: Session):
        super().__init__(RoomType, db)

    def find_by_hotel(self, hotel_id: int) -> List[RoomType]:
        return self.db.query(RoomType).filter(RoomType.hotel_id == hotel_id).all()


class PriceSeasonRepository(BaseRepository[PriceSeason]):
    def __init__(self, db: Session):
        super().__init__(PriceSeason, db)

    def find_by_hotel(self, hotel_id: int) -> List[PriceSeason]:
        return self.db.query(PriceSeason).filter(PriceSeason.hotel_id == hotel_id).all()
