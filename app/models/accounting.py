"""مجال الحسابات — JournalEntry, JournalLine, Account + seeding helpers."""
import datetime
from decimal import Decimal
import re
from sqlalchemy import Column, Integer, String, Date, Text, ForeignKey, Numeric
from sqlalchemy.orm import relationship
from models import Base
from app.models.base import WorkflowMixin
from currency_utils import D, DECIMAL_ZERO


class JournalEntry(WorkflowMixin, Base):
    __tablename__ = "journal_entries"
    id = Column(Integer, primary_key=True)
    entry_number = Column(String, unique=True)
    date = Column(Date, default=datetime.date.today)
    source_type = Column(String)
    source_id = Column(Integer, nullable=True)
    description = Column(String)
    reversed_entry_id = Column(Integer, ForeignKey("journal_entries.id"), nullable=True)
    is_reversal = Column(Integer, default=0)
    lines = relationship("JournalLine", back_populates="entry", cascade="all, delete-orphan")
    reversed_entry = relationship("JournalEntry", remote_side=[id], backref="reversals")

    @property
    def total_debit(self):
        return sum(D(l.debit) for l in self.lines)

    @property
    def total_credit(self):
        return sum(D(l.credit) for l in self.lines)

    @property
    def is_balanced(self):
        return abs(self.total_debit - self.total_credit) < D("0.01")


class JournalLine(Base):
    __tablename__ = "journal_lines"
    id = Column(Integer, primary_key=True)
    entry_id = Column(Integer, ForeignKey("journal_entries.id"))
    account_id = Column(Integer, ForeignKey("accounts.id"))
    debit = Column(Numeric(12,2), default=DECIMAL_ZERO)
    credit = Column(Numeric(12,2), default=DECIMAL_ZERO)
    currency_id = Column(Integer, ForeignKey("currencies.id"), nullable=True)
    exchange_rate = Column(Numeric(12,6), nullable=True)
    amount_in_base_currency = Column(Numeric(12,2), nullable=True)
    cost_center = Column(String, nullable=True)
    branch = Column(String, nullable=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True)
    supplier_id = Column(Integer, ForeignKey("suppliers.id"), nullable=True)
    reservation_id = Column(Integer, ForeignKey("reservations.id"), nullable=True)
    memo = Column(String, nullable=True)
    entry = relationship("JournalEntry", back_populates="lines")
    account = relationship("Account")
    currency = relationship("Currency")
    customer = relationship("Customer")
    supplier = relationship("Supplier")
    reservation = relationship("Reservation")


def generate_journal_entry_number(db):
    year = datetime.date.today().year
    count = db.query(JournalEntry).count() + 1
    return f"JE-{year}-{count:05d}"


class Account(Base):
    __tablename__ = "accounts"
    id = Column(Integer, primary_key=True)
    code = Column(String)
    name = Column(String, nullable=False)
    account_type = Column(String, nullable=False)
    parent_id = Column(Integer, ForeignKey("accounts.id"), nullable=True)
    is_system = Column(Integer, default=0)
    key = Column(String, nullable=True)
    opening_balance = Column(Numeric(12,2), default=DECIMAL_ZERO)
    parent = relationship("Account", remote_side=[id], backref="children")


ACCOUNT_TYPE_LABELS = {
    "asset": "أصول", "liability": "خصوم", "equity": "حقوق ملكية",
    "revenue": "إيرادات", "expense": "مصروفات",
}
ACCOUNT_TYPE_LABELS_EN = {
    "asset": "Assets", "liability": "Liabilities", "equity": "Equity",
    "revenue": "Revenue", "expense": "Expenses",
}
ACCOUNT_NAME_EN = {
    "الأصول": "Assets", "الخصوم": "Liabilities", "حقوق الملكية": "Equity",
    "الإيرادات": "Revenue", "المصروفات": "Expenses",
    "الخزنة والبنوك": "Treasury & Banks",
    "ذمم العملاء (مستحق من العملاء)": "Customer Receivables",
    "ذمم الموردين (مستحق للموردين)": "Supplier Payables",
    "حساب معلق (دفعات وتحصيلات غير موزعة)": "Suspense Account",
    "رأس المال": "Capital", "الأرباح المرحّلة": "Retained Earnings",
    "إيرادات المبيعات (الحجوزات)": "Sales Revenue (Bookings)",
    "تكلفة الحجوزات (الفنادق)": "Booking Cost (Hotels)",
    "عمولات الموظفين والوكلاء": "Employee & Agent Commissions",
    "رواتب الموظفين": "Employee Salaries",
    "مصروفات تشغيلية عامة": "General Operational Expenses",
    "الخزنة الرئيسية": "Main Treasury", "لوحة الخزنة": "Treasury Dashboard",
}
EXPENSE_WORDS_EN = {
    "إيجار": "Rent", "كهرباء": "Electricity", "ماء": "Water", "مياه": "Water",
    "هاتف": "Phone", "انترنت": "Internet", "صيانة": "Maintenance", "وقود": "Fuel",
    "بنزين": "Fuel", "طعام": "Food", "مواصلات": "Transportation",
    "تأمين": "Insurance", "ضرائب": "Taxes", "رسوم": "Fees", "مكتب": "Office",
    "قرطاسية": "Stationery", "طباعة": "Printing", "نظافة": "Cleaning",
    "أمن": "Security", "إعلانات": "Advertising", "تسويق": "Marketing",
    "تدريب": "Training", "سفر": "Travel", "فندق": "Hotel", "ضيافة": "Hospitality",
    "مصروفات متنوعة": "Miscellaneous Expenses",
    "مصروف عام": "General Expense", "أخرى": "Other",
}


def get_account_type_labels(lang="ar"):
    return ACCOUNT_TYPE_LABELS_EN if lang == "en" else ACCOUNT_TYPE_LABELS


def translate_account_name(name, lang="ar"):
    if lang != "en":
        return name
    if name in ACCOUNT_NAME_EN:
        return ACCOUNT_NAME_EN[name]
    m = re.match(r"^خزنة فرعية\s*[-–]\s*فرع\s*(\w+)$", name)
    if m:
        return f"Sub-Treasury - Branch {m.group(1)}"
    return name


NAME_TO_KEY = {
    "الخزنة والبنوك": "treasury", "ذمم العملاء (مستحق من العملاء)": "ar",
    "ذمم الموردين (مستحق للموردين)": "ap",
    "حساب معلق (دفعات وتحصيلات غير موزعة)": "suspense",
    "رأس المال": "capital", "الأرباح المرحّلة": "retained_earnings",
    "إيرادات المبيعات (الحجوزات)": "sales_revenue",
    "تكلفة الحجوزات (الفنادق)": "cogs_hotels",
    "عمولات الموظفين والوكلاء": "commissions",
    "رواتب الموظفين": "salaries", "مصروفات تشغيلية عامة": "opex",
}



