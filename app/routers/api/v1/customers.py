"""
REST API surface. Pure JSON in/out via Pydantic schemas.
This is what enables a future mobile app or external integration
without touching a single line of server-rendered HTML code.
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import List
from app.core.database import get_db
from app.services.customer_service import CustomerService
from app.schemas.customer import CustomerOut, CustomerCreate, CustomerUpdate

router = APIRouter(prefix="/customers", tags=["Customers"])


@router.get("", response_model=List[CustomerOut])
def list_customers(q: str = Query(None), db: Session = Depends(get_db)):
    service = CustomerService(db)
    if q:
        return service.search(q)
    return service.list_customers()


@router.get("/{customer_id}", response_model=CustomerOut)
def get_customer(customer_id: int, db: Session = Depends(get_db)):
    return CustomerService(db).get_customer(customer_id)


@router.post("", response_model=CustomerOut, status_code=201)
def create_customer(payload: CustomerCreate, db: Session = Depends(get_db)):
    return CustomerService(db).create_customer(payload)


@router.put("/{customer_id}", response_model=CustomerOut)
def update_customer(customer_id: int, payload: CustomerUpdate, db: Session = Depends(get_db)):
    return CustomerService(db).update_customer(customer_id, payload)


@router.delete("/{customer_id}", status_code=204)
def delete_customer(customer_id: int, db: Session = Depends(get_db)):
    CustomerService(db).delete_customer(customer_id)
