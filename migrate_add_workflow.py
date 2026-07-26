"""Migration: add workflow columns and set status='posted' for existing records."""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from sqlalchemy import create_engine, text
from models import DATABASE_URL

engine = create_engine(DATABASE_URL)

TABLES = [
    "collections", "supplier_payments", "expenses",
    "employee_withdrawals", "treasury_transactions", "journal_entries",
]
WORKFLOW_COLUMNS = [
    ("status", "VARCHAR(20) DEFAULT 'draft'"),
    ("created_at", "TIMESTAMP"),
    ("created_by", "VARCHAR(100)"),
    ("reviewed_at", "TIMESTAMP"),
    ("reviewed_by", "VARCHAR(100)"),
    ("approved_at", "TIMESTAMP"),
    ("approved_by", "VARCHAR(100)"),
    ("posted_at", "TIMESTAMP"),
    ("posted_by", "VARCHAR(100)"),
    ("cancelled_at", "TIMESTAMP"),
    ("cancelled_by", "VARCHAR(100)"),
    ("cancellation_reason", "VARCHAR(500)"),
]

def get_existing_columns(conn, table):
    rows = conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
    return {r[1] for r in rows}

if __name__ == "__main__":
    with engine.begin() as conn:
        for table in TABLES:
            existing = get_existing_columns(conn, table)
            for col_name, col_type in WORKFLOW_COLUMNS:
                if col_name in existing:
                    print(f"  SKIP ({table}.{col_name} already exists)")
                    continue
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_type}"))
                print(f"  OK ({table}.{col_name} added)")
        for table in TABLES:
            result = conn.execute(text(f"UPDATE {table} SET status='posted' WHERE status IS NULL OR status='draft'"))
            if result.rowcount:
                print(f"  Updated {result.rowcount} rows in {table} to status='posted'")
    print("Migration complete.")
