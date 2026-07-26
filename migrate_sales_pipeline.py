import sqlite3, os
DB_PATH = "tourism_erp.db"
if not os.path.exists(DB_PATH):
    print(f"Database not found at {DB_PATH}"); exit(1)
conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()
cursor.execute("""
    CREATE TABLE IF NOT EXISTS sales_opportunities (
        id INTEGER PRIMARY KEY,
        stage VARCHAR DEFAULT 'Lead',
        customer_id INTEGER NOT NULL REFERENCES customers(id),
        source VARCHAR DEFAULT 'direct',
        destination VARCHAR,
        budget FLOAT DEFAULT 0,
        travel_date DATE,
        travelers_count INTEGER DEFAULT 1,
        probability INTEGER DEFAULT 50,
        expected_value FLOAT DEFAULT 0,
        sales_rep_id INTEGER REFERENCES employees(id),
        next_followup_date DATE,
        loss_reason TEXT,
        notes TEXT,
        created_at TIMESTAMP,
        updated_at TIMESTAMP
    )
""")
conn.commit(); conn.close()
print("[OK] Created table sales_opportunities")
