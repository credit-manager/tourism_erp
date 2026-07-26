"""
Migration: add allow_negative_balance column to treasury_accounts.
"""
import sqlite3
import os

DB_PATH = "tourism_erp.db"

if not os.path.exists(DB_PATH):
    print(f"Database not found at {DB_PATH}")
    exit(1)

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

cursor.execute("PRAGMA table_info(treasury_accounts)")
columns = [row[1] for row in cursor.fetchall()]

if "allow_negative_balance" not in columns:
    cursor.execute("ALTER TABLE treasury_accounts ADD COLUMN allow_negative_balance INTEGER DEFAULT 0")
    print("[OK] Added allow_negative_balance column")
else:
    print("[INFO] Column already exists")

conn.commit()
conn.close()
print("[OK] Migration complete")
