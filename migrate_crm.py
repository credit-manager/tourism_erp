"""
Migration: add CRM fields to customers + create new CRM tables.
"""
import sqlite3, os

DB_PATH = "tourism_erp.db"
if not os.path.exists(DB_PATH):
    print(f"Database not found at {DB_PATH}")
    exit(1)

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

# --- Add columns to customers ---
cursor.execute("PRAGMA table_info(customers)")
existing = {row[1] for row in cursor.fetchall()}

new_cols = {
    "email": "VARCHAR",
    "address": "VARCHAR",
    "city": "VARCHAR",
    "country": "VARCHAR",
    "nationality": "VARCHAR",
    "gender": "VARCHAR",
    "date_of_birth": "DATE",
    "id_number": "VARCHAR",
    "passport_no": "VARCHAR",
    "classification": "VARCHAR DEFAULT 'regular'",
    "source": "VARCHAR DEFAULT 'direct'",
    "account_manager_id": "INTEGER REFERENCES employees(id)",
    "clv": "FLOAT DEFAULT 0",
    "risk_level": "VARCHAR DEFAULT 'low'",
    "credit_limit": "FLOAT DEFAULT 0",
    "last_contact_date": "DATE",
    "preferred_contact_method": "VARCHAR DEFAULT 'phone'",
    "created_at": "TIMESTAMP",
    "updated_at": "TIMESTAMP",
}

for col, coltype in new_cols.items():
    if col not in existing:
        cursor.execute(f"ALTER TABLE customers ADD COLUMN {col} {coltype}")
        print(f"[OK] Added column customers.{col}")

# --- Create new tables ---
new_tables = {
    "customer_contacts": """
        CREATE TABLE IF NOT EXISTS customer_contacts (
            id INTEGER PRIMARY KEY,
            customer_id INTEGER NOT NULL REFERENCES customers(id),
            name VARCHAR NOT NULL,
            phone VARCHAR,
            email VARCHAR,
            job_title VARCHAR,
            is_primary INTEGER DEFAULT 0,
            notes TEXT
        )
    """,
    "customer_quotes": """
        CREATE TABLE IF NOT EXISTS customer_quotes (
            id INTEGER PRIMARY KEY,
            customer_id INTEGER NOT NULL REFERENCES customers(id),
            quote_number VARCHAR UNIQUE,
            date DATE DEFAULT CURRENT_DATE,
            total_amount FLOAT DEFAULT 0,
            status VARCHAR DEFAULT 'draft',
            valid_until DATE,
            notes TEXT,
            created_by VARCHAR,
            created_at TIMESTAMP
        )
    """,
    "customer_tasks": """
        CREATE TABLE IF NOT EXISTS customer_tasks (
            id INTEGER PRIMARY KEY,
            customer_id INTEGER NOT NULL REFERENCES customers(id),
            title VARCHAR NOT NULL,
            description TEXT,
            due_date DATE,
            status VARCHAR DEFAULT 'pending',
            assigned_to_id INTEGER REFERENCES employees(id),
            priority VARCHAR DEFAULT 'normal',
            created_at TIMESTAMP,
            completed_at TIMESTAMP
        )
    """,
    "customer_complaints": """
        CREATE TABLE IF NOT EXISTS customer_complaints (
            id INTEGER PRIMARY KEY,
            customer_id INTEGER NOT NULL REFERENCES customers(id),
            subject VARCHAR NOT NULL,
            description TEXT,
            status VARCHAR DEFAULT 'open',
            resolution TEXT,
            created_at TIMESTAMP,
            resolved_at TIMESTAMP,
            created_by VARCHAR
        )
    """,
    "customer_timeline": """
        CREATE TABLE IF NOT EXISTS customer_timeline (
            id INTEGER PRIMARY KEY,
            customer_id INTEGER NOT NULL REFERENCES customers(id),
            type VARCHAR,
            content TEXT,
            reference_type VARCHAR,
            reference_id INTEGER,
            created_by VARCHAR,
            created_at TIMESTAMP
        )
    """,
}

for name, ddl in new_tables.items():
    cursor.execute(ddl)
    print(f"[OK] Created table {name}")

conn.commit()
conn.close()
print("[OK] Migration complete")
