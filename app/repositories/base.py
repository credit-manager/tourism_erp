"""
Generic repository — encapsulates raw SQLAlchemy access.
Concrete repositories (CustomerRepository, ReservationRepository, ...)
inherit this for the boring CRUD and add domain-specific queries on top.

Why this matters: services NEVER write `db.query(...)` directly.
That means we can swap the persistence engine (e.g. add Redis caching,
or move to async SQLAlchemy) by touching ONLY this layer.
"""
from typing import Generic, TypeVar, Type, Optional, List
from sqlalchemy.orm import Session

ModelType = TypeVar("ModelType")


class BaseRepository(Generic[ModelType]):
    def __init__(self, model: Type[ModelType], db: Session):
        self.model = model
        self.db = db

    def get(self, id: int) -> Optional[ModelType]:
        return self.db.get(self.model, id)

    def list(self, skip: int = 0, limit: int = 200) -> List[ModelType]:
        return self.db.query(self.model).offset(skip).limit(limit).all()

    def create(self, obj: ModelType) -> ModelType:
        self.db.add(obj)
        self.db.flush()
        return obj

    def update(self, obj: ModelType) -> ModelType:
        self.db.flush()
        return obj

    def delete(self, obj: ModelType) -> None:
        self.db.delete(obj)
        self.db.flush()

    def commit(self) -> None:
        self.db.commit()
