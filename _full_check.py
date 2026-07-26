"""
Comprehensive health check script
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tourism_erp.db")

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session
from decimal import Decimal
from datetime import datetime, date

engine = create_engine("sqlite:///" + DB_PATH, connect_args={"check_same_thread": False})
insp = inspect(engine)
db = Session(engine)

print("=" * 80)
print("TOURISM ERP - COMPREHENSIVE HEALTH CHECK")
print("=" * 80)

# Import all models
from models import (
    Base, Customer, CustomerContact, CustomerQuote, CustomerTask, CustomerComplaint,
    CustomerTimeline, Supplier, Hotel, Employee, Booking, Service, Reservation,
    ReservationDocument, WorkflowTask, Collection, CollectionAllocation,
    JournalEntry, JournalLine, Account, EmployeeWithdrawal,
    SupplierPayment, SupplierPaymentAllocation, Attendance, TreasuryAccount,
    TreasuryTransaction, Expense, Transport, Ticket, UmrahPackage,
    TourismFile, PoliceNotification, Contract, User, AuditLog, StateLog,
    Currency, _SysCfg, SalesOpportunity, Quotation, QuotationLineItem, QuotationVersion,
)

# Get all mapped classes
model_classes = {}
for mapper in Base.registry.mappers:
    cls = mapper.class_
    if hasattr(cls, '__tablename__') and hasattr(cls, '__table__'):
        model_classes[cls.__tablename__] = cls

db_tables = set(insp.get_table_names())
model_tables = set(model_classes.keys())

# ============ PART 1: DB vs MODEL COLUMNS ============
print("\n" + "-" * 60)
print("PART 1: DB vs MODEL COLUMN COMPARISON")
print("-" * 60)

db_only = db_tables - model_tables
print("\nTables in DB but NOT in Model:", db_only if db_only else "None OK")

model_only = model_tables - db_tables
print("\nTables in Model but NOT in DB:", model_only if model_only else "None OK")

for table_name in sorted(db_tables & model_tables):
    db_cols = {c['name']: c for c in insp.get_columns(table_name)}
    cls = model_classes[table_name]
    model_cols = {}
    for col in cls.__table__.columns:
        model_cols[col.name] = col

    db_only_cols = set(db_cols.keys()) - set(model_cols.keys())
    mod_only_cols = set(model_cols.keys()) - set(db_cols.keys())

    type_mismatches = []
    for cname in set(db_cols.keys()) & set(model_cols.keys()):
        db_type = str(db_cols[cname]['type'])
        model_type_str = str(model_cols[cname].type)
        db_simple = db_type.replace(' ', '').lower()
        mod_simple = model_type_str.replace(' ', '').lower()
        if db_simple != mod_simple:
            if 'varchar' in db_simple and 'string' in mod_simple:
                pass
            elif db_type == 'VARCHAR' and model_type_str.startswith('VARCHAR'):
                pass
            elif 'numeric' in db_simple and 'numeric' in mod_simple:
                if db_simple != mod_simple:
                    type_mismatches.append((cname, db_type, model_type_str))
            elif 'float' in db_simple and 'numeric' in mod_simple:
                type_mismatches.append((cname, db_type, model_type_str))
            elif 'boolean' in db_simple and 'boolean' in mod_simple:
                pass
            elif db_simple != mod_simple:
                type_mismatches.append((cname, db_type, model_type_str))

    if db_only_cols or mod_only_cols or type_mismatches:
        print(f"\nISSUE Table: {table_name}")
        if db_only_cols:
            print("  In DB only:", sorted(db_only_cols))
        if mod_only_cols:
            print("  In Model only:", sorted(mod_only_cols))
        if type_mismatches:
            for cname, db_t, mod_t in sorted(type_mismatches):
                print("  TYPE MISMATCH: {}: DB={} vs Model={}".format(cname, db_t, mod_t))
    else:
        print("  OK {}: columns match".format(table_name))

# ============ PART 2: DATA INTEGRITY ============
print("\n" + "-" * 60)
print("PART 2: DATA INTEGRITY CHECK")
print("-" * 60)

table_row_counts = {}
for table_name in sorted(db_tables):
    try:
        count = db.execute(text('SELECT COUNT(*) FROM "{}"'.format(table_name))).scalar()
        table_row_counts[table_name] = count
    except Exception as e:
        table_row_counts[table_name] = "ERROR: {}".format(str(e))

print("\nRow counts:")
for t, c in sorted(table_row_counts.items()):
    print("  {:40s} {}".format(t, str(c)))

expected_non_empty = ['customers', 'suppliers', 'hotels', 'employees', 'users', 'currencies',
                      'accounts', 'treasury_accounts']
print("\nEmpty tables that should have data:")
for t in expected_non_empty:
    cnt = table_row_counts.get(t, 0)
    if cnt == 0:
        print("  ISSUE: {} is EMPTY".format(t))

# NULL in required fields
print("\nNULL values in non-nullable fields:")
for table_name in sorted(db_tables & model_tables):
    cls = model_classes[table_name]
    for col in cls.__table__.columns:
        if not col.nullable and col.default is None and col.name != 'id':
            try:
                null_count = db.execute(text('SELECT COUNT(*) FROM "{}" WHERE "{}" IS NULL'.format(table_name, col.name))).scalar()
                if null_count > 0:
                    print("  ISSUE: {}.{}: {} NULL values".format(table_name, col.name, null_count))
            except Exception as e:
                pass

# Orphaned foreign keys
print("\nOrphaned foreign keys:")
for table_name in sorted(db_tables):
    fks = insp.get_foreign_keys(table_name)
    for fk in fks:
        for constrained_col, referred_col in zip(fk['constrained_columns'], fk['referred_columns']):
            referred_table = fk['referred_table']
            try:
                orphan_count = db.execute(text("""
                    SELECT COUNT(*) FROM "{}" t 
                    WHERE t."{}" IS NOT NULL 
                    AND t."{}" NOT IN (SELECT "{}" FROM "{}")
                """.format(table_name, constrained_col, constrained_col, referred_col, referred_table))).scalar()
                if orphan_count > 0:
                    print("  ISSUE: {}.{} -> {}.{}: {} orphans".format(table_name, constrained_col, referred_table, referred_col, orphan_count))
            except Exception as e:
                pass
            break

# Reservation date checks
print("\nReservation checkin/checkout NULL dates:")
null_checkin = db.execute(text("SELECT COUNT(*) FROM reservations WHERE checkin_date IS NULL")).scalar()
null_checkout = db.execute(text("SELECT COUNT(*) FROM reservations WHERE checkout_date IS NULL")).scalar()
print("  NULL checkin_date:", null_checkin)
print("  NULL checkout_date:", null_checkout)

# Very old/future dates
print("\nDates before 2020 or after 2030:")
for table_name in sorted(db_tables):
    cols = insp.get_columns(table_name)
    for col in cols:
        col_type = str(col['type']).upper()
        if 'DATE' in col_type or 'DATETIME' in col_type:
            cn = col['name']
            try:
                count_old = db.execute(text('SELECT COUNT(*) FROM "{}" WHERE "{}" IS NOT NULL AND "{}" < "2020-01-01"'.format(table_name, cn, cn))).scalar()
                if count_old and count_old > 0:
                    print("  ISSUE: {}.{}: {} records before 2020".format(table_name, cn, count_old))
            except:
                pass
            try:
                count_future = db.execute(text('SELECT COUNT(*) FROM "{}" WHERE "{}" IS NOT NULL AND "{}" > "2030-12-31"'.format(table_name, cn, cn))).scalar()
                if count_future and count_future > 0:
                    print("  ISSUE: {}.{}: {} records after 2030".format(table_name, cn, count_future))
            except:
                pass

# Duplicate booking numbers
print("\nDuplicate booking numbers:")
try:
    dups = db.execute(text("""
        SELECT booking_number, COUNT(*) as cnt FROM reservations 
        GROUP BY booking_number HAVING cnt > 1
    """)).fetchall()
    if dups:
        for row in dups:
            print("  ISSUE: {}: {} duplicates".format(row[0], row[1]))
    else:
        print("  OK - No duplicates")
except Exception as e:
    print("  Error:", e)

# ============ PART 3: STATE MACHINE CHECK ============
print("\n" + "-" * 60)
print("PART 3: STATE MACHINE CHECK")
print("-" * 60)

VALID_STATES = ['draft', 'quoted', 'pending_approval', 'confirmed', 'in_service', 'completed', 'cancelled']

try:
    reservations = db.execute(text("SELECT id, booking_number, guest_name, status, checkin_date, checkout_date FROM reservations ORDER BY id")).fetchall()
    print("\nTotal reservations:", len(reservations))
    
    invalid_status = [r for r in reservations if r[3] not in VALID_STATES]
    if invalid_status:
        print("ISSUE - INVALID STATUSES:")
        for r in invalid_status:
            print("  ID={}, booking={}, guest={}, status='{}'".format(r[0], r[1], r[2], r[3]))
    else:
        print("OK - All statuses are valid")
    
    from collections import Counter
    status_counts = Counter(r[3] for r in reservations)
    print("\nStatus distribution:")
    for s in VALID_STATES:
        c = status_counts.get(s, 0)
        print("  {:25s}: {}".format(s, c))
    
    # In-service without dates
    in_service_no_dates = [r for r in reservations if r[3] == 'in_service' and (r[4] is None or r[5] is None)]
    if in_service_no_dates:
        print("\nISSUE - in_service missing checkin/checkout:")
        for r in in_service_no_dates:
            print("  ID={}, booking={}, guest={}, checkin={}, checkout={}".format(r[0], r[1], r[2], r[4], r[5]))
    else:
        print("OK - All in_service have checkin/checkout dates")
    
except Exception as e:
    print("Error:", e)
    import traceback
    traceback.print_exc()

db.close()
print("\n" + "=" * 80)
print("HEALTH CHECK COMPLETE")
print("=" * 80)
