"""
مشاركات الراوترات: دوال وثوابت مساعدة
"""
from fastapi import Request, Depends, Form, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import func, or_
import datetime, os, shutil, uuid, json, io
from urllib.parse import quote

from models import (
    SessionLocal, init_db, Customer, Supplier, Hotel, Employee,
    Booking, TreasuryAccount, TreasuryTransaction, TreasuryTransfer, Expense,
    Service, Reservation, generate_booking_number, User, hash_password,
    verify_password, needs_rehash,
    Contract, generate_contract_number,
    Transport, Ticket, generate_ticket_number,
    UmrahPackage, generate_umrah_number,
    TourismFile, PoliceNotification,
    AuditLog, Currency, _SysCfg,
    Collection, CollectionAllocation, generate_collection_number,
    Account, ACCOUNT_TYPE_LABELS, get_account_type_labels, translate_account_name,
    EmployeeWithdrawal,
    SupplierPayment, SupplierPaymentAllocation, generate_supplier_payment_number,
    Attendance,
    ReservationDocument, STATUS_LABELS, STATUS_LABELS_EN, STATUS_COLORS,
    JournalEntry, JournalLine,
    CustomerContact, CustomerQuote, CustomerTask, CustomerComplaint, CustomerTimeline,
    SalesOpportunity, STAGES,
    Quotation, QuotationLineItem, QuotationVersion,
    RoomType, MealPlan, HotelContract, PriceSeason,
        SeasonRoomPrice, SeasonChildPrice, SeasonExtraBedPrice,
        SeasonSingleSupplement, NationalityPricing,
        BlackoutDate, MinimumStay, CancellationPolicy, HotelTax,
        SupplierConfirmation, SupplierConfirmationLine,
        SupplierInvoice, SupplierInvoiceLine,
        generate_invoice_number, generate_confirmation_number,
        CommissionPolicy, CommissionEntry,
        Shift, Attendance, LeaveRequest, Holiday, LeaveBalance,
    )
import auth
from context import current_user_var
from i18n import I18N, get_text_map
from currency_utils import D, DECIMAL_ZERO
import math as _math

templates = Jinja2Templates(directory="templates")

import json
from decimal import Decimal as _Decimal

class _DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, _Decimal):
            return float(obj)
        return super().default(obj)

_original_dumps = json.dumps
def _patched_dumps(*args, **kwargs):
    kwargs.setdefault("cls", _DecimalEncoder)
    return _original_dumps(*args, **kwargs)

templates.env.filters["tojson"] = lambda v, **kw: __import__("jinja2").utils.htmlsafe_json_dumps(v, dumps=_patched_dumps, **kw)

def safe_format(fmt, value):
    if value is None:
        value = 0
    try:
        return fmt % float(value)
    except Exception:
        return str(value)

templates.env.filters["format"] = safe_format

def currency_filter(value, decimals=2):
    from decimal import Decimal, InvalidOperation
    try:
        val = Decimal(str(value)) if value is not None else Decimal('0')
        fmt = f"{{:.{decimals}f}}"
        return fmt.format(val)
    except (InvalidOperation, ValueError, TypeError):
        return "0.00"

templates.env.filters["c"] = currency_filter
templates.env.filters["currency"] = currency_filter


def t(request: Request, key: str) -> str:
    lang = request.session.get("lang", "en")
    entry = I18N.get(key)
    if not entry:
        return key
    return entry.get(lang, entry.get("en", key))


def get_lang(request: Request) -> str:
    return request.session.get("lang") or request.cookies.get("lang_pref", "en")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _parse_date(s):
    try:
        return datetime.datetime.strptime(s, "%Y-%m-%d").date()
    except Exception:
        return None


# ---- Description Translation ----
import re as _re

_DESC_PATTERNS_EN = [
    (_re.compile(r'^تحصيل سريع لحجز ([\w-]+)\s*[-–]\s*طريقة الدفع:\s*(.+)$'),
     lambda m: f"Quick Collection for Booking {m.group(1)} - Payment Method: {m.group(2)}"),
    (_re.compile(r'^تحصيل حجز ([\w-]+)\s*[-–]\s*(.+?)\s*[-–]\s*(.+)$'),
     lambda m: f"Booking Collection {m.group(1)} - {m.group(2)} - {m.group(3)}"),
    (_re.compile(r'^تحصيل (COL-\S+) - (.+?) - (.+)$'),
     lambda m: f"Collection {m.group(1)} - {m.group(2)} - {m.group(3)}"),
    (_re.compile(r'^سحب موظف:\s*(.+?)\s*\((.+)\)$'),
     lambda m: f"Employee Withdrawal: {m.group(1)} ({_translate_withdrawal(m.group(2))})"),
    (_re.compile(r'^مصروف:\s*(.+)$'),
     lambda m: f"Expense: {__import__('models', fromlist=['EXPENSE_WORDS_EN']).EXPENSE_WORDS_EN.get(m.group(1).strip(), m.group(1))}"),
    (_re.compile(r'^تحصيل (COL-\S+) - (.+)$'),
     lambda m: f"Collection {m.group(1)} - {m.group(2)}"),
    (_re.compile(r'^دفعة لفندق\s*(.+?)(\s*-\s*.+)?$'),
     lambda m: f"Payment to Hotel {m.group(1)}{m.group(2) or ''}"),
    (_re.compile(r'^دفعة حجز ([\w-]+)\s*[-–]\s*(.+)$'),
     lambda m: f"Booking Payment {m.group(1)} - {m.group(2)}"),
    (_re.compile(r'^دفعة ([\w-]+) لمورد\s*(.*)$'),
     lambda m: f"Payment {m.group(1)} to Supplier {m.group(2)}"),
    (_re.compile(r'^حجز جديد\s*[-–]\s*عميل #(\d+)$'),
     lambda m: f"New Booking - Customer #{m.group(1)}"),
    (_re.compile(r'^طريقة الدفع:\s*(.+)$'),
     lambda m: f"Payment Method: {m.group(1)}"),
]

_WITHDRAWAL_TYPE_EN = {
    "advance": "advance", "salary": "salary", "عمولة": "commission",
    "سلفة": "advance", "راتب": "salary", "أخرى": "other",
}

def _translate_withdrawal(t):
    return _WITHDRAWAL_TYPE_EN.get(t, t)

def translate_description(desc, lang="en"):
    if lang != "en" or not desc:
        return desc
    for pattern, replacer in _DESC_PATTERNS_EN:
        m = pattern.match(desc.strip())
        if m:
            try:
                return replacer(m)
            except Exception:
                pass
    return desc


# ---- File Upload ----
UPLOAD_DIR = "static/uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

ALLOWED_UPLOAD_EXTS = {
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".pdf",
    ".doc", ".docx", ".xls", ".xlsx", ".txt",
}
MAX_UPLOAD_SIZE = 10 * 1024 * 1024

class UnsupportedFileType(Exception):
    def __init__(self, ext):
        self.ext = ext

class FileTooLarge(Exception):
    def __init__(self, size):
        self.size = size

def save_upload(file: UploadFile, allowed_exts=None) -> str:
    exts = allowed_exts if allowed_exts is not None else ALLOWED_UPLOAD_EXTS
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in exts:
        raise UnsupportedFileType(ext)
    fname = f"{uuid.uuid4().hex}{ext}"
    dest = os.path.join(UPLOAD_DIR, fname)
    size = 0
    with open(dest, "wb") as f:
        while True:
            chunk = file.file.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            if size > MAX_UPLOAD_SIZE:
                f.close()
                os.remove(dest)
                raise FileTooLarge(size)
            f.write(chunk)
    return f"/static/uploads/{fname}"


# ---- Helper functions from main.py ----
def _apply_reservation_fields(reservation, data, db):
    reservation.guest_name = data["guest_name"]
    reservation.customer_id = int(data["customer_id"]) if data.get("customer_id") and data["customer_id"].strip() else None
    reservation.email = data.get("email", "")
    reservation.is_vip = 1 if data.get("is_vip") else 0
    reservation.special_requests = data.get("special_requests", "")
    reservation.reference_number = data.get("reference_number", "")
    reservation.reservation_type = data.get("reservation_type", "cash")
    reservation.payment_due_date = _parse_date(data.get("payment_due_date"))
    reservation.source = data.get("source", "direct")
    reservation.priority = data.get("priority", "normal")
    reservation.internal_notes = data.get("internal_notes", "")
    reservation.status = data.get("status", reservation.status or "confirmed")
    reservation.checkin_date = _parse_date(data.get("checkin_date"))
    reservation.checkout_date = _parse_date(data.get("checkout_date"))
    reservation.passport_no = data.get("passport_no", "")
    reservation.phone = data.get("phone", "")
    reservation.nationality = data.get("nationality", "")
    reservation.country = data.get("country", "")
    reservation.adults = int(data.get("adults") or 1)
    reservation.children = int(data.get("children") or 0)
    reservation.children_ages = data.get("children_ages", "")
    reservation.hotel_id = int(data["hotel_id"]) if data.get("hotel_id") else None
    reservation.room_type = data.get("room_type", "")
    reservation.stay_type = data.get("stay_type", "")
    reservation.meal_plan = data.get("meal_plan", "")
    reservation.room_count = int(data.get("room_count") or 1)
    reservation.extra_bed = 1 if data.get("extra_bed") else 0
    reservation.checkin_time = data.get("checkin_time", "")
    reservation.checkout_time = data.get("checkout_time", "")
    reservation.stay_cost = D(data.get("stay_cost"))
    reservation.company_cost = D(data.get("company_cost"))
    reservation.discount = D(data.get("discount"))
    reservation.taxes = D(data.get("taxes"))
    reservation.transportation_cost = D(data.get("transportation_cost"))
    reservation.excursions_cost = D(data.get("excursions_cost"))
    reservation.visa_cost = D(data.get("visa_cost"))
    reservation.insurance_cost = D(data.get("insurance_cost"))
    reservation.other_services_cost = D(data.get("other_services_cost"))
    reservation.flight_number = data.get("flight_number", "")
    reservation.pickup_time = data.get("pickup_time", "")
    reservation.dropoff_time = data.get("dropoff_time", "")
    reservation.driver_name = data.get("driver_name", "")
    reservation.guide_name = data.get("guide_name", "")
    reservation.vehicle_info = data.get("vehicle_info", "")
    reservation.ops_supplier_id = int(data["ops_supplier_id"]) if data.get("ops_supplier_id") else None
    reservation.employee_id = int(data["employee_id"]) if data.get("employee_id") else None
    reservation.reservation_rep_commission_type = data.get("reservation_rep_commission_type", "percentage")
    reservation.reservation_rep_commission_value = D(data.get("reservation_rep_commission_value"))
    reservation.travel_agent_id = int(data["travel_agent_id"]) if data.get("travel_agent_id") else None
    reservation.travel_agent_commission_type = data.get("travel_agent_commission_type", "percentage")
    reservation.travel_agent_commission_value = D(data.get("travel_agent_commission_value"))
    reservation.sales_rep_id = int(data["sales_rep_id"]) if data.get("sales_rep_id") else None
    reservation.marketing_rep_id = int(data["marketing_rep_id"]) if data.get("marketing_rep_id") else None
    reservation.marketing_rep_commission_type = data.get("marketing_rep_commission_type", "percentage")
    reservation.marketing_rep_commission_value = D(data.get("marketing_rep_commission_value"))
    reservation.ops_supplier_commission_type = data.get("ops_supplier_commission_type", "percentage")
    reservation.ops_supplier_commission_value = D(data.get("ops_supplier_commission_value"))
    reservation.sales_rep_commission_type = data.get("sales_rep_commission_type", "percentage")
    reservation.sales_rep_commission_value = D(data.get("sales_rep_commission_value"))
    reservation.notes = data.get("notes", "")
    service_ids = data.get("service_ids") or []
    reservation.services = db.query(Service).filter(Service.id.in_(service_ids)).all() if service_ids else []
    base = reservation.total_profit
    reservation.employee_commission = (
        Reservation.compute_commission(reservation.reservation_rep_commission_type, reservation.reservation_rep_commission_value, base)
        if reservation.employee_id else DECIMAL_ZERO
    )
    reservation.travel_agent_commission_amount = (
        Reservation.compute_commission(reservation.travel_agent_commission_type, reservation.travel_agent_commission_value, base)
        if reservation.travel_agent_id else DECIMAL_ZERO
    )
    reservation.sales_rep_commission_amount = (
        Reservation.compute_commission(reservation.sales_rep_commission_type, reservation.sales_rep_commission_value, base)
        if reservation.sales_rep_id else DECIMAL_ZERO
    )
    reservation.marketing_rep_commission_amount = (
        Reservation.compute_commission(reservation.marketing_rep_commission_type, reservation.marketing_rep_commission_value, base)
        if reservation.marketing_rep_id else DECIMAL_ZERO
    )
    reservation.ops_supplier_commission_amount = (
        Reservation.compute_commission(reservation.ops_supplier_commission_type, reservation.ops_supplier_commission_value, base)
        if reservation.ops_supplier_id else DECIMAL_ZERO
    )


def _detect_conflicts(db, guest_name, hotel_id, checkin_date, checkout_date, customer_id=None, exclude_id=None):
    if not (guest_name and hotel_id and checkin_date and checkout_date):
        return []
    query = db.query(Reservation).filter(
        Reservation.hotel_id == hotel_id,
        Reservation.status != "cancelled",
        Reservation.checkin_date < checkout_date,
        Reservation.checkout_date > checkin_date,
    )
    if customer_id:
        query = query.filter(
            or_(Reservation.customer_id == customer_id,
                Reservation.guest_name == guest_name)
        )
    else:
        query = query.filter(Reservation.guest_name == guest_name)
    if exclude_id:
        query = query.filter(Reservation.id != exclude_id)
    return query.all()


def _find_hotel_by_exact_name(db, name):
    clean_name = (name or "").strip()
    if not clean_name:
        return None
    return db.query(Hotel).filter(
        func.lower(func.trim(Hotel.name)) == clean_name.lower()
    ).first()


def _get_or_create_hotel(db, name):
    if not name:
        return None
    name = str(name).strip()
    if not name:
        return None
    hotel = _find_hotel_by_exact_name(db, name)
    if not hotel:
        hotel = Hotel(name=name, price_per_night=0, available_rooms=0)
        db.add(hotel)
        db.flush()
    return hotel


def _get_or_create_employee(db, name):
    if not name:
        return None
    name = str(name).strip()
    if not name:
        return None
    emp = db.query(Employee).filter(Employee.name == name).first()
    if not emp:
        emp = Employee(name=name, salary=0, commission_rate=0)
        db.add(emp)
        db.flush()
    return emp


def _parse_excel_date(val):
    if not val:
        return None
    if isinstance(val, datetime.datetime):
        return val.date()
    if isinstance(val, datetime.date):
        return val
    return _parse_date(str(val).strip()[:10])


def _employee_period_earnings(db, employee_id, period_start, period_end):
    entries = db.query(CommissionEntry).filter(
        CommissionEntry.recipient_id == employee_id,
        CommissionEntry.recipient_type.in_(["employee", "agent"]),
        CommissionEntry.status.in_(["calculated", "earned", "paid"]),
        CommissionEntry.created_at >= period_start,
        CommissionEntry.created_at <= period_end,
    ).all()
    if entries:
        return sum(D(e.calculated_amount) for e in entries)
    reservations = db.query(Reservation).filter(
        Reservation.created_date >= period_start, Reservation.created_date <= period_end
    ).all()
    total = DECIMAL_ZERO
    for r in reservations:
        if r.employee_id == employee_id:
            total += D(r.employee_commission)
        if r.travel_agent_id == employee_id:
            total += D(r.travel_agent_commission_amount)
        if r.sales_rep_id == employee_id:
            total += D(r.sales_rep_commission_amount)
        if r.marketing_rep_id == employee_id:
            total += D(r.marketing_rep_commission_amount)
    return total


def parse_report_dates(date_from: str, date_to: str):
    today = datetime.date.today()
    if date_from:
        try:
            d_from = datetime.datetime.strptime(date_from, "%Y-%m-%d").date()
        except Exception:
            d_from = today.replace(day=1)
    else:
        d_from = today.replace(day=1)
    if date_to:
        try:
            d_to = datetime.datetime.strptime(date_to, "%Y-%m-%d").date()
        except Exception:
            d_to = today
    else:
        d_to = today
    return d_from, d_to


def build_report_data(db, d_from, d_to):
    reservations = (
        db.query(Reservation)
        .filter(Reservation.created_date >= d_from, Reservation.created_date <= d_to)
        .order_by(Reservation.created_date.asc())
        .all()
    )
    expenses = (
        db.query(Expense)
        .filter(Expense.date >= d_from, Expense.date <= d_to)
        .order_by(Expense.date.asc())
        .all()
    )
    def _jbal(key):
        a = db.query(Account).filter(Account.key == key).first()
        if not a:
            return DECIMAL_ZERO
        q = db.query(
            func.coalesce(func.sum(JournalLine.debit), 0),
            func.coalesce(func.sum(JournalLine.credit), 0),
        ).join(JournalEntry).filter(
            JournalLine.account_id == a.id,
            JournalEntry.date >= d_from, JournalEntry.date <= d_to,
        )
        debit, credit = q.first()
        if a.account_type in ("asset", "expense"):
            return D(debit) - D(credit)
        return D(credit) - D(debit)
    total_revenue = _jbal("sales_revenue")
    total_hotel_cost = _jbal("cogs_hotels")
    gross_profit = total_revenue - total_hotel_cost
    total_commissions = _jbal("commissions")
    total_expenses = _jbal("opex")
    net_profit = gross_profit - total_commissions - total_expenses
    expenses_by_category = {}
    for e in expenses:
        expenses_by_category[e.category] = expenses_by_category.get(e.category, DECIMAL_ZERO) + D(e.amount)
    hotel_breakdown = {}
    for r in reservations:
        hname = r.hotel.name if r.hotel else "بدون فندق"
        row = hotel_breakdown.setdefault(hname, {"count": 0, "revenue": DECIMAL_ZERO, "cost": DECIMAL_ZERO})
        row["count"] += 1
        row["revenue"] += D(r.company_cost)
        row["cost"] += D(r.stay_cost)
    return {
        "reservations": reservations,
        "expenses": expenses,
        "total_revenue": total_revenue,
        "total_hotel_cost": total_hotel_cost,
        "gross_profit": gross_profit,
        "total_commissions": total_commissions,
        "total_expenses": total_expenses,
        "net_profit": net_profit,
        "expenses_by_category": expenses_by_category,
        "hotel_breakdown": hotel_breakdown,
    }


def paginate(query, page=1, per_page=50):
    total = query.count()
    total_pages = max(1, _math.ceil(total / per_page))
    page = max(1, min(page, total_pages))
    items = query.offset((page - 1) * per_page).limit(per_page).all()
    return items, page, total_pages, total


def pagination_ctx(page, total_pages, total):
    return {
        "page": page, "total_pages": total_pages, "total": total,
        "has_prev": page > 1, "has_next": page < total_pages,
        "prev_page": page - 1, "next_page": page + 1,
    }


RESERVATION_EXCEL_COLUMNS = [
    ("رقم الحجز", "booking_number"),
    ("تاريخ الحجز", "created_date"),
    ("اسم العميل", "guest_name"),
    ("تاريخ الوصول", "checkin_date"),
    ("تاريخ المغادرة", "checkout_date"),
    ("عدد البالغين", "adults"),
    ("عدد الأطفال", "children"),
    ("أعمار الأطفال", "children_ages"),
    ("الجنسية", "nationality"),
    ("رقم الجواز", "passport_no"),
    ("الهاتف", "phone"),
    ("اسم الفندق", "hotel_name"),
    ("نوع الغرفة", "room_type"),
    ("نوع الإقامة", "stay_type"),
    ("عدد الغرف", "room_count"),
    ("سعر البيع", "company_cost"),
    ("التحصيل", "paid_to_office"),
    ("سعر التكلفة", "stay_cost"),
    ("المدفوع للتكلفة", "paid_to_hotel"),
    ("الانتقالات", "transportation_cost"),
    ("خدمات أخرى", "other_services_cost"),
    ("مسؤول الحجز", "employee_name"),
    ("نوع عمولة مسؤول الحجز", "reservation_rep_commission_type"),
    ("قيمة عمولة مسؤول الحجز", "reservation_rep_commission_value"),
    ("وكيل السفر", "travel_agent_name"),
    ("نوع عمولة وكيل السفر", "travel_agent_commission_type"),
    ("قيمة عمولة وكيل السفر", "travel_agent_commission_value"),
    ("مسؤول المبيعات", "sales_rep_name"),
    ("نوع عمولة مسؤول المبيعات", "sales_rep_commission_type"),
    ("قيمة عمولة مسؤول المبيعات", "sales_rep_commission_value"),
    ("ملاحظات", "notes"),
]
