from decimal import Decimal
from sqlalchemy import Column, Integer, String, Float, Date, DateTime, Time, ForeignKey, Text, Table, event, Numeric, Boolean, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.orm import sessionmaker
from currency_utils import D, DECIMAL_ZERO
import datetime
import json
from context import current_user_var

from app.models.base import Base, engine, SessionLocal, DATABASE_URL, WorkflowMixin, Currency, ExchangeRate, _SysCfg





# ---------------------- سجل تتبع العمليات (Audit Log) ----------------------
def _describe_instance(obj):
    """وصف مختصر للسجل المتأثر عشان يبان في اللوج بشكل مفهوم"""
    for attr in ("booking_number", "contract_number", "ticket_number", "package_number",
                 "guest_name", "name", "title", "username", "group_leader", "pilgrim_name"):
        val = getattr(obj, attr, None)
        if val:
            return str(val)[:120]
    return ""


@event.listens_for(SessionLocal, "before_flush")
def _audit_log_before_flush(session, flush_context, instances):
    user = current_user_var.get()
    if user is None:
        return  # عمليات تتم بدون مستخدم (مثل init_db الأولي) لا تُسجَّل

    changes = []
    for obj in list(session.new):
        if isinstance(obj, AuditLog):
            continue
        changes.append(("create", obj))
    for obj in list(session.dirty):
        if isinstance(obj, AuditLog):
            continue
        if session.is_modified(obj, include_collections=False):
            changes.append(("update", obj))
    for obj in list(session.deleted):
        if isinstance(obj, AuditLog):
            continue
        changes.append(("delete", obj))

    for action, obj in changes:
        table = getattr(obj, "__tablename__", type(obj).__name__)
        session.add(AuditLog(
            timestamp=datetime.datetime.utcnow(),
            username=getattr(user, "username", "?"),
            role=getattr(user, "role", "?"),
            action=action,
            table_name=table,
            record_id=getattr(obj, "id", None),
            summary=_describe_instance(obj),
        ))





# ---------------------- تهيئة شجرة الحسابات (Chart of Accounts Seeds) ----------------------
def _backfill_account_keys(db):
    changed = False
    for acc in db.query(Account).filter(Account.is_system == 1).all():
        if not acc.key and acc.name in NAME_TO_KEY:
            acc.key = NAME_TO_KEY[acc.name]
            changed = True
    if changed:
        db.commit()


def _seed_cash_closing_accounts(db):
    expense = db.query(Account).filter(Account.account_type == "expense", Account.parent_id == None).first()
    revenue = db.query(Account).filter(Account.account_type == "revenue", Account.parent_id == None).first()
    if expense and not db.query(Account).filter(Account.key == "cash_shortage").first():
        db.add(Account(name="فرق الجرد (عجز)", account_type="expense", parent_id=expense.id, is_system=1, key="cash_shortage"))
    if revenue and not db.query(Account).filter(Account.key == "cash_surplus").first():
        db.add(Account(name="فرق الجرد (زيادة)", account_type="revenue", parent_id=revenue.id, is_system=1, key="cash_surplus"))


def seed_exchange_rates(db):
    base = db.query(Currency).filter(Currency.is_base == 1).first()
    others = db.query(Currency).filter(Currency.is_base == 0).all()
    today = datetime.date.today()
    if base and others and not db.query(ExchangeRate).filter(ExchangeRate.date == today).first():
        for c in others:
            db.add(ExchangeRate(currency_id=c.id, date=today, buy_rate=c.exchange_rate, sell_rate=c.exchange_rate))
        db.commit()


def seed_chart_of_accounts(db):
    if db.query(Account).first():
        _backfill_account_keys(db)
        return
    assets = Account(name="الأصول", account_type="asset", is_system=1)
    liabilities = Account(name="الخصوم", account_type="liability", is_system=1)
    equity = Account(name="حقوق الملكية", account_type="equity", is_system=1)
    revenue = Account(name="الإيرادات", account_type="revenue", is_system=1)
    expense = Account(name="المصروفات", account_type="expense", is_system=1)
    db.add_all([assets, liabilities, equity, revenue, expense])
    db.flush()
    db.add_all([
        Account(name="الخزنة والبنوك", account_type="asset", parent_id=assets.id, is_system=1, key="treasury"),
        Account(name="ذمم العملاء (مستحق من العملاء)", account_type="asset", parent_id=assets.id, is_system=1, key="ar"),
        Account(name="ذمم الموردين (مستحق للموردين)", account_type="liability", parent_id=liabilities.id, is_system=1, key="ap"),
        Account(name="حساب معلق (دفعات وتحصيلات غير موزعة)", account_type="liability", parent_id=liabilities.id, is_system=1, key="suspense"),
        Account(name="رأس المال", account_type="equity", parent_id=equity.id, is_system=1, key="capital"),
        Account(name="الأرباح المرحّلة", account_type="equity", parent_id=equity.id, is_system=1, key="retained_earnings"),
        Account(name="إيرادات المبيعات (الحجوزات)", account_type="revenue", parent_id=revenue.id, is_system=1, key="sales_revenue"),
        Account(name="تكلفة الحجوزات (الفنادق)", account_type="expense", parent_id=expense.id, is_system=1, key="cogs_hotels"),
        Account(name="عمولات الموظفين والوكلاء", account_type="expense", parent_id=expense.id, is_system=1, key="commissions"),
        Account(name="رواتب الموظفين", account_type="expense", parent_id=expense.id, is_system=1, key="salaries"),
        Account(name="مصروفات تشغيلية عامة", account_type="expense", parent_id=expense.id, is_system=1, key="opex"),
        Account(name="فرق الجرد (عجز)", account_type="expense", parent_id=expense.id, is_system=1, key="cash_shortage"),
        Account(name="فرق الجرد (زيادة)", account_type="revenue", parent_id=revenue.id, is_system=1, key="cash_surplus"),
    ])
    db.commit()


# ---------------------- كشف حساب بنكي (Bank Reconciliation) ----------------------
from app.models.bank import BankStatement, BankTransaction


# ─── Commission Policies & Entries ─────────────────────────────
from app.models.commission import CommissionPolicy, CommissionEntry


# ─── Payroll Run ──────────────────────────────────────────
from app.models.payroll import PayrollRun, PayrollRunItem


# ─── Hotel domain ───────────────────────────────────────────────
from app.models.hotel import Hotel, RoomType, MealPlan, HotelContract, PriceSeason, SeasonRoomPrice, SeasonChildPrice, SeasonExtraBedPrice, SeasonSingleSupplement, NationalityPricing, BlackoutDate, MinimumStay, CancellationPolicy, HotelTax


# ─── Customer domain ────────────────────────────────────────────
from app.models.customer import Customer, CustomerContact, CustomerQuote, CustomerTask, CustomerComplaint, CustomerTimeline, SalesOpportunity


# ─── Reservation domain ─────────────────────────────────────────
from app.models.reservation import Booking, Service, Reservation, reservation_services, ReservationDocument, WorkflowTask, StateLog, STATUS_LABELS, STATUS_LABELS_EN, STATUS_COLORS, generate_booking_number


# ─── Supplier domain ────────────────────────────────────────────
from app.models.supplier import Supplier, SupplierPayment, SupplierPaymentAllocation, SupplierConfirmation, SupplierConfirmationLine, SupplierInvoice, SupplierInvoiceLine, generate_supplier_payment_number, generate_invoice_number, generate_confirmation_number


# ─── Employee domain ────────────────────────────────────────────
from app.models.employee import Employee, Department, EmployeeWithdrawal, Shift, Attendance, LeaveRequest, Holiday, LeaveBalance, LEAVE_TYPES, LEAVE_STATUSES
from app.models.notification import Notification


# ─── Accounting domain ──────────────────────────────────────────
from app.models.accounting import JournalEntry, JournalLine, Account, ACCOUNT_TYPE_LABELS, ACCOUNT_TYPE_LABELS_EN, ACCOUNT_NAME_EN, EXPENSE_WORDS_EN, get_account_type_labels, translate_account_name, NAME_TO_KEY, generate_journal_entry_number


# ─── Treasury domain ────────────────────────────────────────────
from app.models.treasury import TreasuryAccount, DefaultTreasuryAccount, TreasuryTransfer, CashClosing, TreasuryTransaction, Expense


# ─── Transport domain ───────────────────────────────────────────
from app.models.transport import Transport, Ticket, generate_ticket_number


# ─── Quotation domain ───────────────────────────────────────────
from app.models.quotation import STAGES, Contract, generate_contract_number, Quotation, QuotationLineItem, QuotationVersion, UmrahPackage, generate_umrah_number


# ─── User / Auth domain ─────────────────────────────────────────
from app.models.user import User, AuditLog, LoginAttempt, UserSession, PasswordResetToken, hash_password, _hash_password_legacy, verify_password, needs_rehash


# ─── Files / Security domain ────────────────────────────────────
from app.models.files import TourismFile, SecureFile, PoliceNotification


# ─── Collection domain ──────────────────────────────────────────
from app.models.collection import Collection, CollectionAllocation, generate_collection_number


# ─── Base / Shared domain ───────────────────────────────────────
from app.models.base import WorkflowMixin, Currency, ExchangeRate, _SysCfg


def init_db():
    """تهيئة قاعدة البيانات: الإنشاء التلقائي للجداول + البيانات الابتدائية.
    ملاحظة: التعديلات على الـ schema تتم عبر Alembic migrations (migrations/versions/)
    """
    Base.metadata.create_all(bind=engine)
    import sqlite3 as _sqlite3
    try:
        _conn = _sqlite3.connect("tourism_erp.db")
        _c = _conn.cursor()
        for _sql in [
            "ALTER TABLE treasury_accounts ADD COLUMN type VARCHAR DEFAULT 'treasury'",
            "ALTER TABLE treasury_accounts ADD COLUMN allow_negative_balance BOOLEAN DEFAULT 0",
            "ALTER TABLE treasury_accounts ADD COLUMN currency_id INTEGER REFERENCES currencies(id)",
            "ALTER TABLE collections ADD COLUMN account_id INTEGER REFERENCES treasury_accounts(id)",
            "ALTER TABLE supplier_payments ADD COLUMN account_id INTEGER REFERENCES treasury_accounts(id)",
            "ALTER TABLE expenses ADD COLUMN account_id INTEGER REFERENCES treasury_accounts(id)",
            "ALTER TABLE bookings ADD COLUMN account_id INTEGER REFERENCES treasury_accounts(id)",
            "ALTER TABLE cash_closings ADD COLUMN account_id INTEGER REFERENCES treasury_accounts(id)",
            "ALTER TABLE cash_closings ADD COLUMN closing_date DATE",
            "ALTER TABLE cash_closings ADD COLUMN system_balance NUMERIC(12,2) DEFAULT 0",
            "ALTER TABLE cash_closings ADD COLUMN actual_balance NUMERIC(12,2) DEFAULT 0",
            "ALTER TABLE cash_closings ADD COLUMN difference NUMERIC(12,2) DEFAULT 0",
            "ALTER TABLE cash_closings ADD COLUMN reason VARCHAR",
            "ALTER TABLE cash_closings ADD COLUMN attachment_path VARCHAR",
        ]:
            try:
                _c.execute(_sql)
            except _sqlite3.OperationalError:
                pass
        _c.execute("UPDATE treasury_accounts SET type='treasury' WHERE type IS NULL")
        try:
            _c.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_attendance_employee_date ON attendance(employee_id, date)")
        except _sqlite3.OperationalError:
            pass
        for _sql2 in [
            "ALTER TABLE attendance ADD COLUMN shift_id INTEGER REFERENCES shifts(id)",
            "ALTER TABLE attendance ADD COLUMN check_in DATETIME",
            "ALTER TABLE attendance ADD COLUMN check_out DATETIME",
            "ALTER TABLE attendance ADD COLUMN work_hours NUMERIC(6,2) DEFAULT 0",
            "ALTER TABLE attendance ADD COLUMN late_minutes INTEGER DEFAULT 0",
            "ALTER TABLE attendance ADD COLUMN overtime_hours NUMERIC(6,2) DEFAULT 0",
            "ALTER TABLE attendance ADD COLUMN approved INTEGER DEFAULT 0",
            "ALTER TABLE attendance ADD COLUMN approved_by INTEGER REFERENCES users(id)",
            "ALTER TABLE employees ADD COLUMN annual_leave_entitlement INTEGER DEFAULT 21",
        ]:
            try:
                _c.execute(_sql2)
            except _sqlite3.OperationalError:
                pass
        for _sql in [
            "ALTER TABLE treasury_transfers ADD COLUMN from_account_id INTEGER REFERENCES treasury_accounts(id)",
            "ALTER TABLE treasury_transfers ADD COLUMN to_account_id INTEGER REFERENCES treasury_accounts(id)",
            "ALTER TABLE treasury_transfers ADD COLUMN converted_amount NUMERIC(12,2) DEFAULT 0",
            "ALTER TABLE treasury_transfers ADD COLUMN exchange_rate NUMERIC(12,6) DEFAULT 1.0",
            "ALTER TABLE treasury_transfers ADD COLUMN fee NUMERIC(12,2) DEFAULT 0",
            "ALTER TABLE treasury_transfers ADD COLUMN net_amount NUMERIC(12,2) DEFAULT 0",
            "ALTER TABLE cash_closings ADD COLUMN account_id INTEGER REFERENCES treasury_accounts(id)",
            "ALTER TABLE cash_closings ADD COLUMN closing_date DATE",
            "ALTER TABLE cash_closings ADD COLUMN system_balance NUMERIC(12,2) DEFAULT 0",
            "ALTER TABLE cash_closings ADD COLUMN actual_balance NUMERIC(12,2) DEFAULT 0",
            "ALTER TABLE cash_closings ADD COLUMN difference NUMERIC(12,2) DEFAULT 0",
            "ALTER TABLE cash_closings ADD COLUMN reason VARCHAR",
            "ALTER TABLE cash_closings ADD COLUMN attachment_path VARCHAR",
            "ALTER TABLE exchange_rates ADD COLUMN currency_id INTEGER REFERENCES currencies(id)",
            "ALTER TABLE exchange_rates ADD COLUMN date DATE",
            "ALTER TABLE exchange_rates ADD COLUMN buy_rate NUMERIC(12,6) DEFAULT 1.0",
            "ALTER TABLE exchange_rates ADD COLUMN sell_rate NUMERIC(12,6) DEFAULT 1.0",
            "ALTER TABLE collections ADD COLUMN currency_id INTEGER REFERENCES currencies(id)",
            "ALTER TABLE collections ADD COLUMN amount_currency NUMERIC(12,2) DEFAULT 0",
            "ALTER TABLE collections ADD COLUMN amount_base NUMERIC(12,2) DEFAULT 0",
            "ALTER TABLE collections ADD COLUMN exchange_rate NUMERIC(12,6) DEFAULT 1.0",
            "ALTER TABLE supplier_payments ADD COLUMN currency_id INTEGER REFERENCES currencies(id)",
            "ALTER TABLE supplier_payments ADD COLUMN amount_currency NUMERIC(12,2) DEFAULT 0",
            "ALTER TABLE supplier_payments ADD COLUMN amount_base NUMERIC(12,2) DEFAULT 0",
            "ALTER TABLE supplier_payments ADD COLUMN exchange_rate NUMERIC(12,6) DEFAULT 1.0",
            "ALTER TABLE expenses ADD COLUMN currency_id INTEGER REFERENCES currencies(id)",
            "ALTER TABLE expenses ADD COLUMN amount_currency NUMERIC(12,2) DEFAULT 0",
            "ALTER TABLE expenses ADD COLUMN amount_base NUMERIC(12,2) DEFAULT 0",
            "ALTER TABLE expenses ADD COLUMN exchange_rate NUMERIC(12,6) DEFAULT 1.0",
            "ALTER TABLE bookings ADD COLUMN currency_id INTEGER REFERENCES currencies(id)",
            "ALTER TABLE bookings ADD COLUMN amount_currency NUMERIC(12,2) DEFAULT 0",
            "ALTER TABLE bookings ADD COLUMN amount_base NUMERIC(12,2) DEFAULT 0",
            "ALTER TABLE bookings ADD COLUMN exchange_rate NUMERIC(12,6) DEFAULT 1.0",
            "ALTER TABLE transports ADD COLUMN currency_id INTEGER REFERENCES currencies(id)",
            "ALTER TABLE transports ADD COLUMN amount_currency NUMERIC(12,2) DEFAULT 0",
            "ALTER TABLE transports ADD COLUMN amount_base NUMERIC(12,2) DEFAULT 0",
            "ALTER TABLE transports ADD COLUMN exchange_rate NUMERIC(12,6) DEFAULT 1.0",
            "ALTER TABLE tickets ADD COLUMN currency_id INTEGER REFERENCES currencies(id)",
            "ALTER TABLE tickets ADD COLUMN amount_currency NUMERIC(12,2) DEFAULT 0",
            "ALTER TABLE tickets ADD COLUMN amount_base NUMERIC(12,2) DEFAULT 0",
            "ALTER TABLE tickets ADD COLUMN exchange_rate NUMERIC(12,6) DEFAULT 1.0",
            "ALTER TABLE umrah_packages ADD COLUMN currency_id INTEGER REFERENCES currencies(id)",
            "ALTER TABLE umrah_packages ADD COLUMN amount_currency NUMERIC(12,2) DEFAULT 0",
            "ALTER TABLE umrah_packages ADD COLUMN amount_base NUMERIC(12,2) DEFAULT 0",
            "ALTER TABLE umrah_packages ADD COLUMN exchange_rate NUMERIC(12,6) DEFAULT 1.0",
            "ALTER TABLE supplier_confirmations ADD COLUMN currency_id INTEGER REFERENCES currencies(id)",
            "ALTER TABLE supplier_confirmations ADD COLUMN amount_currency NUMERIC(12,2) DEFAULT 0",
            "ALTER TABLE supplier_confirmations ADD COLUMN amount_base NUMERIC(12,2) DEFAULT 0",
            "ALTER TABLE supplier_confirmations ADD COLUMN exchange_rate NUMERIC(12,6) DEFAULT 1.0",
            "ALTER TABLE supplier_invoices ADD COLUMN currency_id INTEGER REFERENCES currencies(id)",
            "ALTER TABLE supplier_invoices ADD COLUMN amount_currency NUMERIC(12,2) DEFAULT 0",
            "ALTER TABLE supplier_invoices ADD COLUMN amount_base NUMERIC(12,2) DEFAULT 0",
            "ALTER TABLE supplier_invoices ADD COLUMN exchange_rate NUMERIC(12,6) DEFAULT 1.0",
            "ALTER TABLE treasury_transactions ADD COLUMN reference VARCHAR",
            "ALTER TABLE treasury_transactions ADD COLUMN currency_id INTEGER REFERENCES currencies(id)",
            "ALTER TABLE treasury_transactions ADD COLUMN amount_currency NUMERIC(12,2) DEFAULT 0",
            "ALTER TABLE treasury_transactions ADD COLUMN amount_base NUMERIC(12,2) DEFAULT 0",
            "ALTER TABLE treasury_transactions ADD COLUMN exchange_rate NUMERIC(12,6) DEFAULT 1.0",
            "ALTER TABLE bank_statements ADD COLUMN account_id INTEGER REFERENCES treasury_accounts(id)",
            "ALTER TABLE bank_statements ADD COLUMN period_start DATE",
            "ALTER TABLE bank_statements ADD COLUMN period_end DATE",
            "ALTER TABLE bank_statements ADD COLUMN opening_balance NUMERIC(12,2) DEFAULT 0",
            "ALTER TABLE bank_statements ADD COLUMN closing_balance NUMERIC(12,2) DEFAULT 0",
            "ALTER TABLE bank_statements ADD COLUMN file_path VARCHAR",
            "ALTER TABLE bank_statements ADD COLUMN status VARCHAR DEFAULT 'imported'",
            "ALTER TABLE employees ADD COLUMN housing_allowance NUMERIC(12,2) DEFAULT 0",
            "ALTER TABLE employees ADD COLUMN transport_allowance NUMERIC(12,2) DEFAULT 0",
            "ALTER TABLE employees ADD COLUMN other_allowances NUMERIC(12,2) DEFAULT 0",
            "ALTER TABLE employees ADD COLUMN social_insurance NUMERIC(12,2) DEFAULT 0",
            "ALTER TABLE employees ADD COLUMN hire_date DATE",
            "ALTER TABLE bank_statements ADD COLUMN created_by VARCHAR",
            "ALTER TABLE bank_transactions ADD COLUMN statement_id INTEGER REFERENCES bank_statements(id)",
            "ALTER TABLE bank_transactions ADD COLUMN date DATE",
            "ALTER TABLE bank_transactions ADD COLUMN description VARCHAR",
            "ALTER TABLE bank_transactions ADD COLUMN reference VARCHAR",
            "ALTER TABLE bank_transactions ADD COLUMN debit NUMERIC(12,2) DEFAULT 0",
            "ALTER TABLE bank_transactions ADD COLUMN credit NUMERIC(12,2) DEFAULT 0",
            "ALTER TABLE bank_transactions ADD COLUMN balance NUMERIC(12,2)",
            "ALTER TABLE bank_transactions ADD COLUMN matched_txn_id INTEGER REFERENCES treasury_transactions(id)",
            "ALTER TABLE bank_transactions ADD COLUMN match_status VARCHAR DEFAULT 'unmatched'",
            "ALTER TABLE bank_transactions ADD COLUMN notes VARCHAR",
        ]:
            try:
                _c.execute(_sql)
            except _sqlite3.OperationalError:
                pass
        for _sql in [
            "ALTER TABLE users ADD COLUMN mfa_secret VARCHAR",
            "ALTER TABLE users ADD COLUMN mfa_enabled INTEGER DEFAULT 0",
            "ALTER TABLE users ADD COLUMN password_changed_at DATETIME",
            "ALTER TABLE users ADD COLUMN failed_login_count INTEGER DEFAULT 0",
            "ALTER TABLE users ADD COLUMN locked_until DATETIME",
        ]:
            try:
                _c.execute(_sql)
            except _sqlite3.OperationalError:
                pass
        try:
            import os as _os
            _os.makedirs("backups", exist_ok=True)
        except Exception:
            pass
        _conn.commit()
        _conn.close()
    except Exception:
        pass
    db = SessionLocal()
    if not db.query(Currency).first():
        db.add_all([
            Currency(code="EGP", name="جنيه مصري", symbol="ج.م", exchange_rate=1.0, is_base=1),
            Currency(code="USD", name="دولار أمريكي", symbol="$", exchange_rate=48.0, is_base=0),
            Currency(code="SAR", name="ريال سعودي", symbol="ر.س", exchange_rate=12.8, is_base=0),
        ])
        db.commit()
    base_currency = db.query(Currency).filter(Currency.is_base == 1).first()
    if not db.query(TreasuryAccount).first():
        db.add_all([
            TreasuryAccount(name="الخزنة الرئيسية", type="treasury", balance=0, currency_id=base_currency.id if base_currency else None),
            TreasuryAccount(name="خزنة فرعية - فرع 1", type="treasury", balance=0, currency_id=base_currency.id if base_currency else None),
            TreasuryAccount(name="البنك الرئيسي", type="bank", balance=0, currency_id=base_currency.id if base_currency else None),
            TreasuryAccount(name="محفظة إلكترونية", type="wallet", balance=0, currency_id=base_currency.id if base_currency else None),
        ])
    if not db.query(DefaultTreasuryAccount).first():
        main_treasury = db.query(TreasuryAccount).filter(TreasuryAccount.name == "الخزنة الرئيسية").first()
        if main_treasury:
            db.add_all([
                DefaultTreasuryAccount(operation_type="collection", branch="main", account_id=main_treasury.id),
                DefaultTreasuryAccount(operation_type="supplier_payment", branch="main", account_id=main_treasury.id),
                DefaultTreasuryAccount(operation_type="expense", branch="main", account_id=main_treasury.id),
                DefaultTreasuryAccount(operation_type="withdrawal", branch="main", account_id=main_treasury.id),
            ])
    if not db.query(User).first():
        import secrets as _sec
        _admin_pw = _sec.token_hex(12)
        db.add(User(
            username="admin", password_hash=hash_password(_admin_pw),
            full_name="مدير النظام", role="admin", is_active=1,
            extra_permissions="[]", revoked_permissions="[]",
        ))
        print()
        print("=" * 50)
        print("تم إنشاء حساب admin بكلمة مرور عشوائية:")
        print("اسم المستخدم: admin")
        print("كلمة المرور:", _admin_pw)
        print("=" * 50)
    _seed_cash_closing_accounts(db)
    seed_exchange_rates(db)
    db.commit()
    seed_chart_of_accounts(db)
    db.close()



