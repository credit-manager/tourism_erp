"""مجال المستخدمين والصلاحيات — User, AuditLog, LoginAttempt, UserSession, PasswordResetToken + hash utilities."""
import datetime
import hashlib
import json
from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey
from sqlalchemy.orm import relationship
from models import Base

try:
    import bcrypt as _bcrypt
except ImportError:
    _bcrypt = None

_LEGACY_SALT = "tourism_erp_salt::"


def hash_password(password: str) -> str:
    if _bcrypt:
        return _bcrypt.hashpw(password.encode("utf-8"), _bcrypt.gensalt()).decode("utf-8")
    return hashlib.sha256((_LEGACY_SALT + password).encode()).hexdigest()


def _hash_password_legacy(password: str) -> str:
    return hashlib.sha256((_LEGACY_SALT + password).encode()).hexdigest()


def verify_password(password: str, stored_hash: str) -> bool:
    if not stored_hash:
        return False
    if stored_hash.startswith("$2") and _bcrypt:
        try:
            return _bcrypt.checkpw(password.encode("utf-8"), stored_hash.encode("utf-8"))
        except ValueError:
            return False
    return stored_hash == _hash_password_legacy(password)


def needs_rehash(stored_hash: str) -> bool:
    return bool(_bcrypt) and not (stored_hash or "").startswith("$2")


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    username = Column(String, unique=True, nullable=False)
    password_hash = Column(String, nullable=False)
    full_name = Column(String)
    role = Column(String, default="reservations")
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=True)
    is_active = Column(Integer, default=1)
    extra_permissions = Column(Text, default="[]")
    revoked_permissions = Column(Text, default="[]")
    mfa_secret = Column(String, nullable=True)
    mfa_enabled = Column(Integer, default=0)
    password_changed_at = Column(DateTime, nullable=True)
    failed_login_count = Column(Integer, default=0)
    locked_until = Column(DateTime, nullable=True)
    employee = relationship("Employee")

    def get_extra(self):
        try:
            return set(json.loads(self.extra_permissions or "[]"))
        except Exception:
            return set()

    def get_revoked(self):
        try:
            return set(json.loads(self.revoked_permissions or "[]"))
        except Exception:
            return set()


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id = Column(Integer, primary_key=True)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)
    username = Column(String)
    role = Column(String)
    action = Column(String)
    table_name = Column(String)
    record_id = Column(Integer, nullable=True)
    summary = Column(String)
    old_values = Column(Text, nullable=True)
    new_values = Column(Text, nullable=True)
    reason = Column(String, nullable=True)


class LoginAttempt(Base):
    __tablename__ = "login_attempts"
    id = Column(Integer, primary_key=True)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)
    username = Column(String, nullable=True)
    ip = Column(String, nullable=True)
    user_agent = Column(String, nullable=True)
    success = Column(Integer, default=0)
    reason = Column(String, nullable=True)
    user_id = Column(Integer, nullable=True)


class UserSession(Base):
    __tablename__ = "user_sessions"
    id = Column(Integer, primary_key=True)
    token = Column(String, unique=True, nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    ip = Column(String, nullable=True)
    user_agent = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    last_seen = Column(DateTime, default=datetime.datetime.utcnow)
    is_active = Column(Integer, default=1)
    user = relationship("User")


class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    token = Column(String, unique=True, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)
    used = Column(Integer, default=0)
    ip = Column(String, nullable=True)
    user = relationship("User")
