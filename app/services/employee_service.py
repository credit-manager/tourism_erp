"""Service layer: employee business logic."""
from typing import List, Optional
from datetime import date
from sqlalchemy.orm import Session
from app.repositories.employee_repository import EmployeeRepository, AttendanceRepository
from models import Employee, Attendance


class EmployeeService:
    def __init__(self, db: Session):
        self.repo = EmployeeRepository(db)
        self.attendance = AttendanceRepository(db)

    def search(self, q: str) -> List[Employee]:
        return self.repo.search(q)

    def get(self, eid: int) -> Optional[Employee]:
        return self.repo.get(eid)
