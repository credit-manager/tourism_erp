"""Employee repository."""
from typing import Optional, List
from sqlalchemy.orm import Session
from app.repositories.base import BaseRepository
from models import Employee, Attendance, LeaveRequest


class EmployeeRepository(BaseRepository[Employee]):
    def __init__(self, db: Session):
        super().__init__(Employee, db)

    def search(self, q: str) -> List[Employee]:
        pat = f"%{q}%"
        return self.db.query(Employee).filter(Employee.name.ilike(pat)).all()


class AttendanceRepository(BaseRepository[Attendance]):
    def __init__(self, db: Session):
        super().__init__(Attendance, db)

    def find_by_employee_and_date(self, emp_id: int, dt) -> Optional[Attendance]:
        return self.db.query(Attendance).filter(
            Attendance.employee_id == emp_id, Attendance.date == dt
        ).first()

    def find_by_employee_range(self, emp_id: int, start, end) -> List[Attendance]:
        return self.db.query(Attendance).filter(
            Attendance.employee_id == emp_id,
            Attendance.date >= start,
            Attendance.date <= end,
        ).all()
