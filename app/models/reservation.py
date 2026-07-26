"""مجال الحجوزات — Booking, Service, Reservation, ReservationDocument, WorkflowTask, StateLog, reservation_services."""
import datetime
from decimal import Decimal
from sqlalchemy import Column, Integer, String, Date, DateTime, Text, ForeignKey, Numeric, Table
from sqlalchemy.orm import relationship
from models import Base
from currency_utils import D, DECIMAL_ZERO


class Booking(Base):
    __tablename__ = "bookings"
    id = Column(Integer, primary_key=True)
    customer_id = Column(Integer, ForeignKey("customers.id"))
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=True)
    supplier_id = Column(Integer, ForeignKey("suppliers.id"), nullable=True)
    hotel_id = Column(Integer, ForeignKey("hotels.id"), nullable=True)
    booking_type = Column(String, default="internal")  # internal/external/flight
    date = Column(Date, default=datetime.date.today)
    total_price = Column(Numeric(12,2), default=DECIMAL_ZERO)
    supplier_cost = Column(Numeric(12,2), default=DECIMAL_ZERO)
    company_commission = Column(Numeric(12,2), default=DECIMAL_ZERO)
    employee_commission = Column(Numeric(12,2), default=DECIMAL_ZERO)
    status = Column(String, default="confirmed")  # pending/confirmed/cancelled
    account_id = Column(Integer, ForeignKey("treasury_accounts.id"), nullable=True)
    currency_id = Column(Integer, ForeignKey("currencies.id"), nullable=True)
    amount_currency = Column(Numeric(12,2), default=DECIMAL_ZERO)
    amount_base = Column(Numeric(12,2), default=DECIMAL_ZERO)
    exchange_rate = Column(Numeric(12,6), default=Decimal("1.0"))

    customer = relationship("Customer", back_populates="bookings")
    account = relationship("TreasuryAccount", foreign_keys=[account_id])
    currency = relationship("Currency")
    employee = relationship("Employee", back_populates="bookings")
    supplier = relationship("Supplier", back_populates="bookings")
    hotel = relationship("Hotel")


class Service(Base):
    __tablename__ = "services"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    price = Column(Numeric(12,2), default=DECIMAL_ZERO)
    image_path = Column(String)


reservation_services = Table(
    "reservation_services", Base.metadata,
    Column("reservation_id", Integer, ForeignKey("reservations.id")),
    Column("service_id", Integer, ForeignKey("services.id")),
)


class Reservation(Base):
    __tablename__ = "reservations"
    id = Column(Integer, primary_key=True)
    booking_number = Column(String, unique=True)
    created_date = Column(Date, default=datetime.date.today)
    reference_number = Column(String)
    reservation_type = Column(String, default="cash")      # cash / credit
    payment_due_date = Column(Date, nullable=True)
    source = Column(String, default="direct")
    priority = Column(String, default="normal")
    internal_notes = Column(Text)

    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True)
    guest_name = Column(String, nullable=False)
    email = Column(String)
    is_vip = Column(Integer, default=0)
    special_requests = Column(Text)
    checkin_date = Column(Date)
    checkout_date = Column(Date)
    passport_no = Column(String)
    phone = Column(String)
    nationality = Column(String)
    country = Column(String)

    adults = Column(Integer, default=1)
    children = Column(Integer, default=0)
    children_ages = Column(String)

    hotel_id = Column(Integer, ForeignKey("hotels.id"))
    room_type = Column(String)
    stay_type = Column(String)
    meal_plan = Column(String)
    room_count = Column(Integer, default=1)
    extra_bed = Column(Integer, default=0)
    checkin_time = Column(String)
    checkout_time = Column(String)

    stay_cost = Column(Numeric(12,2), default=DECIMAL_ZERO)
    paid_to_hotel = Column(Numeric(12,2), default=DECIMAL_ZERO)

    company_cost = Column(Numeric(12,2), default=DECIMAL_ZERO)
    discount = Column(Numeric(12,2), default=DECIMAL_ZERO)
    taxes = Column(Numeric(12,2), default=DECIMAL_ZERO)
    paid_to_office = Column(Numeric(12,2), default=DECIMAL_ZERO)

    transportation_cost = Column(Numeric(12,2), default=DECIMAL_ZERO)
    excursions_cost = Column(Numeric(12,2), default=DECIMAL_ZERO)
    visa_cost = Column(Numeric(12,2), default=DECIMAL_ZERO)
    insurance_cost = Column(Numeric(12,2), default=DECIMAL_ZERO)
    other_services_cost = Column(Numeric(12,2), default=DECIMAL_ZERO)

    flight_number = Column(String)
    pickup_time = Column(String)
    dropoff_time = Column(String)
    driver_name = Column(String)
    guide_name = Column(String)
    vehicle_info = Column(String)
    ops_supplier_id = Column(Integer, ForeignKey("suppliers.id"), nullable=True)

    employee_id = Column(Integer, ForeignKey("employees.id"))
    reservation_rep_commission_type = Column(String, default="percentage")
    reservation_rep_commission_value = Column(Numeric(12,2), default=DECIMAL_ZERO)
    employee_commission = Column(Numeric(12,2), default=DECIMAL_ZERO)

    travel_agent_id = Column(Integer, ForeignKey("customers.id"), nullable=True)
    travel_agent_commission_type = Column(String, default="percentage")
    travel_agent_commission_value = Column(Numeric(12,2), default=DECIMAL_ZERO)
    travel_agent_commission_amount = Column(Numeric(12,2), default=DECIMAL_ZERO)

    sales_rep_id = Column(Integer, ForeignKey("employees.id"), nullable=True)
    sales_rep_commission_type = Column(String, default="percentage")
    sales_rep_commission_value = Column(Numeric(12,2), default=DECIMAL_ZERO)
    sales_rep_commission_amount = Column(Numeric(12,2), default=DECIMAL_ZERO)

    marketing_rep_id = Column(Integer, ForeignKey("employees.id"), nullable=True)
    marketing_rep_commission_type = Column(String, default="percentage")
    marketing_rep_commission_value = Column(Numeric(12,2), default=DECIMAL_ZERO)
    marketing_rep_commission_amount = Column(Numeric(12,2), default=DECIMAL_ZERO)

    ops_supplier_commission_type = Column(String, default="percentage")
    ops_supplier_commission_value = Column(Numeric(12,2), default=DECIMAL_ZERO)
    ops_supplier_commission_amount = Column(Numeric(12,2), default=DECIMAL_ZERO)

    status = Column(String, default="confirmed")
    cancelled_at = Column(DateTime, nullable=True)
    cancelled_by = Column(String, nullable=True)
    cancellation_reason = Column(String, nullable=True)
    notes = Column(Text)

    hotel = relationship("Hotel")
    customer = relationship("Customer", foreign_keys=[customer_id])
    ops_supplier = relationship("Supplier")
    employee = relationship("Employee", back_populates="reservations", foreign_keys=[employee_id])
    travel_agent = relationship("Customer", foreign_keys=[travel_agent_id], back_populates="travel_agent_reservations")
    sales_rep = relationship("Employee", foreign_keys=[sales_rep_id], back_populates="sales_rep_reservations")
    marketing_rep = relationship("Employee", foreign_keys=[marketing_rep_id], back_populates="marketing_rep_reservations")
    services = relationship("Service", secondary=reservation_services)
    collection_allocations = relationship("CollectionAllocation", back_populates="reservation")
    documents = relationship("ReservationDocument", back_populates="reservation", cascade="all, delete-orphan")

    @property
    def computed_paid_to_office(self):
        from decimal import Decimal
        if not self.collection_allocations:
            return Decimal("0.00")
        return sum(D(a.amount) for a in self.collection_allocations)

    @property
    def nights(self):
        if self.checkin_date and self.checkout_date and self.checkout_date > self.checkin_date:
            return (self.checkout_date - self.checkin_date).days
        return 0

    @property
    def total_room_nights(self):
        return (self.room_count or 0) * self.nights

    @property
    def remaining_to_hotel(self):
        return D(self.stay_cost) - D(self.paid_to_hotel)

    @property
    def net_sale_price(self):
        return D(self.company_cost) - D(self.discount) + D(self.taxes)

    @property
    def remaining_to_office(self):
        return self.net_sale_price - D(self.paid_to_office)

    @property
    def initial_profit(self):
        return self.net_sale_price - D(self.stay_cost)

    @property
    def profit(self):
        return self.initial_profit

    @property
    def gross_profit(self):
        return self.initial_profit

    @property
    def total_profit(self):
        return self.initial_profit - (
            D(self.transportation_cost) + D(self.excursions_cost)
            + D(self.visa_cost) + D(self.insurance_cost) + D(self.other_services_cost)
        )

    @property
    def net_profit(self):
        return self.total_profit

    @property
    def total_commissions(self):
        return (D(self.employee_commission) + D(self.travel_agent_commission_amount)
                + D(self.sales_rep_commission_amount) + D(self.marketing_rep_commission_amount)
                + D(self.ops_supplier_commission_amount))

    @property
    def final_company_profit(self):
        return self.total_profit - self.total_commissions

    @property
    def is_paid_in_full(self):
        return bool(self.net_sale_price) and self.remaining_to_office <= D("0.009")

    @property
    def services_total(self):
        return sum(D(s.price) for s in self.services)

    @staticmethod
    def compute_commission(commission_type, commission_value, base_amount):
        cv = D(commission_value)
        ba = D(base_amount)
        if commission_type == "fixed":
            return cv
        return ba * (cv / D("100"))


STATUS_LABELS = {
    "draft": "مسودة", "quoted": "تم عرض السعر", "pending_approval": "بانتظار الموافقة",
    "confirmed": "مؤكد", "in_service": "قيد التنفيذ",
    "completed": "مكتمل", "cancelled": "ملغي",
}
STATUS_LABELS_EN = {
    "draft": "Draft", "quoted": "Quoted", "pending_approval": "Pending Approval",
    "confirmed": "Confirmed", "in_service": "In Service",
    "completed": "Completed", "cancelled": "Cancelled",
}
STATUS_COLORS = {
    "draft": "neutral", "quoted": "info", "pending_approval": "warning",
    "confirmed": "success", "in_service": "primary",
    "completed": "success", "cancelled": "danger",
}


class ReservationDocument(Base):
    __tablename__ = "reservation_documents"
    id = Column(Integer, primary_key=True)
    reservation_id = Column(Integer, ForeignKey("reservations.id"))
    doc_type = Column(String, default="other")
    file_path = Column(String)
    original_name = Column(String)
    uploaded_at = Column(Date, default=datetime.date.today)

    reservation = relationship("Reservation", back_populates="documents")


class WorkflowTask(Base):
    __tablename__ = "workflow_tasks"
    id = Column(Integer, primary_key=True)
    reservation_id = Column(Integer, ForeignKey("reservations.id"), nullable=False, index=True)
    title = Column(String, nullable=False)
    description = Column(Text)
    assigned_to_id = Column(Integer, ForeignKey("employees.id"), nullable=True)
    due_date = Column(Date, nullable=True)
    priority = Column(String, default="normal")
    status = Column(String, default="pending")
    reminder = Column(Integer, default=0)
    reminded_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    notes = Column(Text)

    reservation = relationship("Reservation", backref="workflow_tasks")
    assigned_to = relationship("Employee")


class StateLog(Base):
    __tablename__ = "state_logs"
    id = Column(Integer, primary_key=True)
    reservation_id = Column(Integer, ForeignKey("reservations.id"), nullable=False, index=True)
    from_state = Column(String, nullable=False)
    to_state = Column(String, nullable=False)
    transition = Column(String, nullable=False)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)
    user_id = Column(Integer, nullable=True)
    username = Column(String, nullable=True)
    reason = Column(String, nullable=True)

    reservation = relationship("Reservation", backref="state_logs")


def generate_booking_number(db):
    year = datetime.date.today().year
    count = db.query(Reservation).count() + 1
    return f"BK-{year}-{count:06d}"
