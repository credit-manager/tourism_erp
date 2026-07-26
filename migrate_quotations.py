import sqlite3, os
DB_PATH = "tourism_erp.db"
if not os.path.exists(DB_PATH):
    print(f"Database not found at {DB_PATH}"); exit(1)
conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()
cursor.execute("""
    CREATE TABLE IF NOT EXISTS quotations (
        id INTEGER PRIMARY KEY,
        quote_number VARCHAR NOT NULL UNIQUE,
        customer_id INTEGER NOT NULL REFERENCES customers(id),
        validity_date DATE,
        status VARCHAR DEFAULT 'draft',
        discount_type VARCHAR DEFAULT 'fixed',
        discount_value NUMERIC(12,2) DEFAULT 0,
        tax_percentage NUMERIC(12,2) DEFAULT 0,
        tax_amount NUMERIC(12,2) DEFAULT 0,
        profit_margin NUMERIC(12,2) DEFAULT 0,
        subtotal NUMERIC(12,2) DEFAULT 0,
        grand_total NUMERIC(12,2) DEFAULT 0,
        notes TEXT,
        terms_conditions TEXT,
        version INTEGER DEFAULT 1,
        reservation_id INTEGER REFERENCES reservations(id),
        created_by VARCHAR,
        created_at TIMESTAMP,
        updated_at TIMESTAMP
    )
""")
cursor.execute("""
    CREATE TABLE IF NOT EXISTS quotation_line_items (
        id INTEGER PRIMARY KEY,
        quotation_id INTEGER NOT NULL REFERENCES quotations(id),
        item_type VARCHAR NOT NULL,
        description VARCHAR,
        item_data TEXT,
        cost_price NUMERIC(12,2) DEFAULT 0,
        sale_price NUMERIC(12,2) DEFAULT 0,
        qty INTEGER DEFAULT 1,
        total NUMERIC(12,2) DEFAULT 0
    )
""")
cursor.execute("""
    CREATE TABLE IF NOT EXISTS quotation_versions (
        id INTEGER PRIMARY KEY,
        quotation_id INTEGER NOT NULL REFERENCES quotations(id),
        version INTEGER NOT NULL,
        pdf_path VARCHAR,
        snapshot TEXT,
        created_at TIMESTAMP
    )
""")
conn.commit(); conn.close()
print("[OK] Created tables: quotations, quotation_line_items, quotation_versions")
