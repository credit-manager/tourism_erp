"""إضافة نظام الأقسام (Departments) — جدول جديد + عمود ربط في الموظفين"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from models import SessionLocal, Base, engine, Department
from sqlalchemy import text

# 1) إنشاء جدول departments (لو مش موجود) عن طريق SQLAlchemy metadata مباشرة
Department.__table__.create(bind=engine, checkfirst=True)
print("  + جدول departments جاهز")

# 2) إضافة الأعمدة الجديدة لجدول employees
db = SessionLocal()
migrations = [
    ("employees", "department_id", "INTEGER REFERENCES departments(id)"),
    ("employees", "job_title", "VARCHAR"),
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
db.close()
print("Done.")
