import sqlite3, hashlib, secrets, os

DB_PATH = os.path.join(os.path.dirname(__file__), "tourism_erp.db")

# توليد كلمة مرور قوية عشوائية
_password = secrets.token_hex(12)
SALT = "tourism_erp_salt::"

def _h(p):
    return hashlib.sha256((SALT + p).encode()).hexdigest()

_u = "owner"
db = sqlite3.connect(DB_PATH)
ex = db.execute("SELECT id FROM users WHERE username=?", (_u,)).fetchone()
if ex:
    db.execute("UPDATE users SET password_hash=?, role='owner', is_active=1 WHERE username=?", (_h(_password), _u))
else:
    db.execute("INSERT INTO users (username, password_hash, full_name, role, is_active, extra_permissions, revoked_permissions) VALUES (?,?,?,?,1,'[]','[]')", (_u, _h(_password), "System"))
db.commit()
db.close()
print("=" * 50)
print("حساب المالك (owner) تم إنشاؤه/تحديثه")
print("اسم المستخدم: owner")
print("كلمة المرور:", _password)
print("=" * 50)
