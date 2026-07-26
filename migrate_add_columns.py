"""إضافة الأعمدة الجديدة إلى قاعدة البيانات الموجودة"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from models import SessionLocal
from sqlalchemy import text

db = SessionLocal()
migrations = [
    ("reservations", "cancelled_at", "DATETIME"),
    ("reservations", "cancelled_by", "VARCHAR"),
    ("reservations", "cancellation_reason", "VARCHAR"),
    ("audit_logs", "old_values", "TEXT"),
    ("audit_logs", "new_values", "TEXT"),
    ("audit_logs", "reason", "VARCHAR"),
]
for table, col, col_type in migrations:
    try:
        db.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {col_type}"))
        db.commit()
        print(f"  + {table}.{col}")
    except Exception as e:
        err = str(e)
        if "duplicate column" in err.lower() or "already exists" in err.lower():
            print(f"  = {table}.{col} already exists")
        else:
            print(f"  - {table}.{col}: {err[:80]}")
db.close()
print("Done.")
