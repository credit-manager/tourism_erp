from typing import Optional, List
from sqlalchemy.orm import Session
from app.repositories.base import BaseRepository
from app.models.customer import Customer


class CustomerRepository(BaseRepository[Customer]):
    def __init__(self, db: Session):
        super().__init__(Customer, db)

    def find_by_phone(self, phone: str) -> Optional[Customer]:
        return self.db.query(Customer).filter(Customer.phone == phone).first()

    def search(self, query: str) -> List[Customer]:
        like = f"%{query}%"
        return self.db.query(Customer).filter(
            (Customer.name.ilike(like)) | (Customer.phone.ilike(like))
        ).all()
