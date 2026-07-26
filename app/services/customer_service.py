"""
Service layer: pure business logic. No `Request`, no `Depends`, no Jinja.
This is what makes it callable identically from:
  - the HTML router (server-rendered pages)
  - the REST API router (JSON)
  - a background job / CLI script / test suite
"""
from typing import List, Optional
from sqlalchemy.orm import Session
from app.repositories.customer_repository import CustomerRepository
from app.models.customer import Customer
from app.schemas.customer import CustomerCreate, CustomerUpdate
from app.core.exceptions import NotFoundError, DuplicateError


class CustomerService:
    def __init__(self, db: Session):
        self.repo = CustomerRepository(db)

    def list_customers(self, skip: int = 0, limit: int = 200) -> List[Customer]:
        return self.repo.list(skip, limit)

    def get_customer(self, customer_id: int) -> Customer:
        customer = self.repo.get(customer_id)
        if not customer:
            raise NotFoundError(f"Customer {customer_id} not found")
        return customer

    def search(self, query: str) -> List[Customer]:
        return self.repo.search(query)

    def create_customer(self, data: CustomerCreate) -> Customer:
        if data.phone and self.repo.find_by_phone(data.phone):
            raise DuplicateError("A customer with this phone number already exists")
        customer = Customer(name=data.name, type=data.type, phone=data.phone, balance=0.0)
        self.repo.create(customer)
        self.repo.commit()
        return customer

    def update_customer(self, customer_id: int, data: CustomerUpdate) -> Customer:
        customer = self.get_customer(customer_id)
        customer.name, customer.type, customer.phone = data.name, data.type, data.phone
        self.repo.update(customer)
        self.repo.commit()
        return customer

    def delete_customer(self, customer_id: int) -> None:
        customer = self.get_customer(customer_id)
        self.repo.delete(customer)
        self.repo.commit()
