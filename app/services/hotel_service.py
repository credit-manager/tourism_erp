"""Service layer: hotel business logic."""
from typing import List, Optional
from sqlalchemy.orm import Session
from app.repositories.hotel_repository import HotelRepository, RoomTypeRepository, PriceSeasonRepository
from models import Hotel, RoomType, PriceSeason


class HotelService:
    def __init__(self, db: Session):
        self.repo = HotelRepository(db)
        self.rooms = RoomTypeRepository(db)
        self.seasons = PriceSeasonRepository(db)

    def search(self, q: str) -> List[Hotel]:
        return self.repo.search(q)

    def get(self, hid: int) -> Optional[Hotel]:
        return self.repo.get(hid)

    def get_rooms(self, hotel_id: int) -> List[RoomType]:
        return self.rooms.find_by_hotel(hotel_id)

    def get_seasons(self, hotel_id: int) -> List[PriceSeason]:
        return self.seasons.find_by_hotel(hotel_id)
