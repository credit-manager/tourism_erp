"""توحيد نظام العمولات — إضافة accrued/source لجدول commission_entries"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from models import SessionLocal
from sqlalchemy import text

db = SessionLocal()
migrations = [
    ("commission_entries", "accrued", "INTEGER DEFAULT 0"),
    ("commission_entries", "source", "VARCHAR DEFAULT 'policy'"),
]
for table, col, col_type in migrations:
    try:
        db.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {col_type}"))
        db.commit()
        print(f"  + {table}.{col}")
    except Exception as e:
        db.rollback()
        err = str(e)
        if "duplicate column" in err.lower() or "already exists" in err.lower():
            print(f"  = {table}.{col} already exists")
        else:
            print(f"  - {table}.{col}: {err[:80]}")

# القيود الموجودة قبل كده كلها كانت من محرك السياسات (مفيش نظام موحّد قبل
# كده) -- نعلّمها source='policy' بشكل صريح للوضوح (accrued تفضل 0 الافتراضي)
db.execute(text("UPDATE commission_entries SET source = 'policy' WHERE source IS NULL"))
db.commit()
db.close()
print("Done.")
