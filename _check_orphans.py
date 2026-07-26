import sys
sys.path.insert(0, r'C:\Users\MG\Downloads\tourism_erp_updated\tourism_erp')
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session

engine = create_engine('sqlite:///C:\\Users\\MG\\Downloads\\tourism_erp_updated\\tourism_erp\\tourism_erp.db', connect_args={"check_same_thread": False})
db = Session(engine)

print("=== reservation_services columns ===")
insp = inspect(engine)
for c in insp.get_columns('reservation_services'):
    print(' ', c['name'], c['type'])

print("\n=== ORPHAN CHECK ===")
tables_check = [
    ('reservations','hotel_id','hotels','id'),
    ('reservations','customer_id','customers','id'),
    ('reservations','employee_id','employees','id'),
    ('reservations','travel_agent_id','customers','id'),
    ('reservations','sales_rep_id','employees','id'),
    ('reservations','marketing_rep_id','employees','id'),
    ('reservations','ops_supplier_id','suppliers','id'),
    ('collection_allocations','collection_id','collections','id'),
    ('collection_allocations','reservation_id','reservations','id'),
    ('state_logs','reservation_id','reservations','id'),
    ('workflow_tasks','reservation_id','reservations','id'),
    ('workflow_tasks','assigned_to_id','employees','id'),
    ('employee_withdrawals','employee_id','employees','id'),
    ('hotels','supplier_id','suppliers','id'),
    ('supplier_payments','supplier_id','suppliers','id'),
    ('collections','customer_id','customers','id'),
    ('quotations','customer_id','customers','id'),
    ('sales_opportunities','customer_id','customers','id'),
    ('transports','supplier_id','suppliers','id'),
    ('tickets','employee_id','employees','id'),
    ('umrah_packages','employee_id','employees','id'),
    ('police_notifications','hotel_id','hotels','id'),
    ('contracts','supplier_id','suppliers','id'),
    ('contracts','hotel_id','hotels','id'),
    ('attendance','employee_id','employees','id'),
    ('journal_lines','account_id','accounts','id'),
    ('journal_lines','entry_id','journal_entries','id'),
    ('journal_lines','currency_id','currencies','id'),
    ('journal_lines','customer_id','customers','id'),
    ('journal_lines','supplier_id','suppliers','id'),
    ('journal_lines','reservation_id','reservations','id'),
]

for tbl, fk_col, ref_tbl, ref_col in tables_check:
    try:
        q = 'SELECT COUNT(*) AS c FROM "{}" t WHERE t."{}" IS NOT NULL AND t."{}" NOT IN (SELECT "{}" FROM "{}")'
        count = db.execute(text(q.format(tbl, fk_col, fk_col, ref_col, ref_tbl))).scalar()
        if count and count > 0:
            print('ORPHAN: {}.{} -> {}.{}: {} orphans'.format(tbl, fk_col, ref_tbl, ref_col, count))
    except Exception as e:
        print('ERROR {}.{}: {}'.format(tbl, fk_col, e))

print("\n=== STATE MACHINE CHECK ===")
# List all reservations with status
rows = db.execute(text("SELECT id, booking_number, guest_name, status, checkin_date, checkout_date FROM reservations ORDER BY id")).fetchall()
print("Total reservations:", len(rows))
print("Status distribution:")
from collections import Counter
status_counts = Counter(r[3] for r in rows)
for s, c in sorted(status_counts.items()):
    print("  {:25s}: {}".format(s, c))
in_service_missing = [r for r in rows if r[3] == 'in_service' and (r[4] is None or r[5] is None)]
if in_service_missing:
    print("\nISSUE - in_service missing checkin/checkout:")
    for r in in_service_missing:
        print("  ID={}, booking={}, guest={}, checkin={}, checkout={}".format(r[0], r[1], repr(r[2]), r[4], r[5]))

# Check for very old/future dates in specific tables
print("\n=== DATE ANOMALIES ===")
date_cols = [
    ('reservations', 'checkin_date'),
    ('reservations', 'checkout_date'),
    ('reservations', 'created_date'),
    ('collections', 'date'),
    ('expenses', 'date'),
    ('journal_entries', 'date'),
    ('quotations', 'validity_date'),
    ('umrah_packages', 'departure_date'),
    ('umrah_packages', 'return_date'),
]
for tbl, col in date_cols:
    try:
        old = db.execute(text("SELECT COUNT(*) FROM \"{}\" WHERE \"{}\" IS NOT NULL AND \"{}\" < '2020-01-01'".format(tbl, col, col))).scalar()
        if old:
            print("BEFORE 2020: {}.{}: {} records".format(tbl, col, old))
    except:
        pass
    try:
        future = db.execute(text("SELECT COUNT(*) FROM \"{}\" WHERE \"{}\" IS NOT NULL AND \"{}\" > '2030-12-31'".format(tbl, col, col))).scalar()
        if future:
            print("AFTER 2030: {}.{}: {} records".format(tbl, col, future))
    except:
        pass

# NULL checkin/checkout
null_ci = db.execute(text("SELECT id, booking_number FROM reservations WHERE checkin_date IS NULL")).fetchall()
null_co = db.execute(text("SELECT id, booking_number FROM reservations WHERE checkout_date IS NULL")).fetchall()
print("\nNULL checkin_date: {} reservations".format(len(null_ci)))
print("NULL checkout_date: {} reservations".format(len(null_co)))
if null_ci:
    print("Sample NULL checkin IDs:", [r[0] for r in null_ci[:10]])

db.close()
print("\nDONE")
