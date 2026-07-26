"""
Pydantic schemas: the ONLY shape of data allowed to cross the HTTP boundary
on the REST API. This is what makes /api/v1 auto-documented (OpenAPI/Swagger)
and type-safe for any client (mobile app, integration, etc).
"""
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class CustomerBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    type: str = Field("B2C", pattern="^(B2C|B2B)$")
    phone: Optional[str] = None


class CustomerCreate(CustomerBase):
    pass


class CustomerUpdate(CustomerBase):
    pass


class CustomerOut(CustomerBase):
    id: int
    balance: float
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True   # allows CustomerOut.model_validate(orm_object)
