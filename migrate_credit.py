import sqlite3

DB = "tourism_erp.db"

conn = sqlite3.connect(DB)
c = conn.cursor()

# Check and add payment_terms to customers
c.execute("PRAGMA table_info(customers)")
cols = {r[1] for r in c.fetchall()}
if "payment_terms" not in cols:
    c.execute("ALTER TABLE customers ADD COLUMN payment_terms TEXT DEFAULT 'due_on_receipt'")
    print("+ added payment_terms to customers")

# Check and add reservation_type to reservations
c.execute("PRAGMA table_info(reservations)")
cols = {r[1] for r in c.fetchall()}
if "reservation_type" not in cols:
    c.execute("ALTER TABLE reservations ADD COLUMN reservation_type TEXT DEFAULT 'cash'")
    print("+ added reservation_type to reservations")
if "payment_due_date" not in cols:
    c.execute("ALTER TABLE reservations ADD COLUMN payment_due_date DATE")
    print("+ added payment_due_date to reservations")

conn.commit()
conn.close()
print("Migration complete.")
