"""مجال الموظفين — Employee, Department, EmployeeWithdrawal, Shift, Attendance, LeaveRequest, Holiday, LeaveBalance."""
import datetime
from sqlalchemy import Column, Integer, String, Date, DateTime, Time, Text, ForeignKey, Numeric, UniqueConstraint
from sqlalchemy.orm import relationship
from models import Base
from app.models.base import WorkflowMixin
from currency_utils import DECIMAL_ZERO


class Department(Base):
    __tablename__ = "departments"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    name_en = Column(String, nullable=True)
    manager_id = Column(Integer, ForeignKey("employees.id"), nullable=True)
    notes = Column(Text)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    manager = relationship("Employee", foreign_keys=[manager_id])
    employees = relationship("Employee", back_populates="department",
                             foreign_keys="Employee.department_id")


class Employee(Base):
    __tablename__ = "employees"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    department_id = Column(Integer, ForeignKey("departments.id"), nullable=True)
    job_title = Column(String, nullable=True)
    salary = Column(Numeric(12,2), default=DECIMAL_ZERO)
    commission_rate = Column(Numeric(12,2), default=DECIMAL_ZERO)
    housing_allowance = Column(Numeric(12,2), default=DECIMAL_ZERO)
    transport_allowance = Column(Numeric(12,2), default=DECIMAL_ZERO)
    other_allowances = Column(Numeric(12,2), default=DECIMAL_ZERO)
    social_insurance = Column(Numeric(12,2), default=DECIMAL_ZERO)
    hire_date = Column(Date, nullable=True)
    annual_leave_entitlement = Column(Integer, default=21)
    bookings = relationship("Booking", back_populates="employee")
    reservations = relationship("Reservation", back_populates="employee", foreign_keys="Reservation.employee_id")
    sales_rep_reservations = relationship("Reservation", back_populates="sales_rep", foreign_keys="Reservation.sales_rep_id")
    marketing_rep_reservations = relationship("Reservation", back_populates="marketing_rep", foreign_keys="Reservation.marketing_rep_id")
    department = relationship("Department", back_populates="employees", foreign_keys=[department_id])


class EmployeeWithdrawal(WorkflowMixin, Base):
    __tablename__ = "employee_withdrawals"
    id = Column(Integer, primary_key=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False)
    account_id = Column(Integer, ForeignKey("treasury_accounts.id"), nullable=True)
    amount = Column(Numeric(12,2), default=DECIMAL_ZERO)
    withdrawal_type = Column(String, default="advance")  # advance / salary
    date = Column(Date, default=datetime.date.today)
    notes = Column(Text)

    employee = relationship("Employee")
    account = relationship("TreasuryAccount")


class Shift(Base):
    __tablename__ = "shifts"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    start_time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=False)
    is_active = Column(Integer, default=1)

    def __repr__(self):
        return f"{self.name} ({self.start_time}→{self.end_time})"


class Attendance(Base):
    __tablename__ = "attendance"
    id = Column(Integer, primary_key=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False)
    shift_id = Column(Integer, ForeignKey("shifts.id"), nullable=True)
    date = Column(Date, nullable=False)
    check_in = Column(DateTime, nullable=True)
    check_out = Column(DateTime, nullable=True)
    work_hours = Column(Numeric(6,2), default=DECIMAL_ZERO)
    late_minutes = Column(Integer, default=0)
    overtime_hours = Column(Numeric(6,2), default=DECIMAL_ZERO)
    status = Column(String, default="present")
    approved = Column(Integer, default=0)
    approved_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    notes = Column(Text)

    employee = relationship("Employee")
    shift = relationship("Shift")
    approver = relationship("User", foreign_keys=[approved_by])

    __table_args__ = (
        UniqueConstraint("employee_id", "date", name="uq_attendance_employee_date"),
    )


LEAVE_TYPES = {"annual": "سنوية", "sick": "مرضية", "emergency": "طارئة", "unpaid": "بدون راتب"}
LEAVE_STATUSES = {"pending": "قيد الانتظار", "approved": "معتمدة", "rejected": "مرفوضة"}


class LeaveRequest(Base):
    __tablename__ = "leave_requests"
    id = Column(Integer, primary_key=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False)
    leave_type = Column(String, nullable=False)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    reason = Column(Text, default="")
    status = Column(String, default="pending")
    approved_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.now)

    employee = relationship("Employee")
    approver = relationship("User", foreign_keys=[approved_by])


class Holiday(Base):
    __tablename__ = "holidays"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    date = Column(Date, nullable=False)
    is_recurring = Column(Integer, default=0)

    __table_args__ = (
        UniqueConstraint("name", "date", name="uq_holiday_name_date"),
    )


class LeaveBalance(Base):
    __tablename__ = "leave_balances"
    id = Column(Integer, primary_key=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False)
    year = Column(Integer, nullable=False)
    entitlement = Column(Integer, default=21)
    used = Column(Integer, default=0)
    remaining = Column(Integer, default=21)

    employee = relationship("Employee")

    __table_args__ = (
        UniqueConstraint("employee_id", "year", name="uq_leave_balance_emp_year"),
    )
