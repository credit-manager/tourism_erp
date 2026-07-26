# -*- coding: utf-8 -*-
"""
menu_config.py
===============
إعدادات القائمة الجانبية على مستوى النظام كله: اتجاه القائمة (طولي/أفقي)
وإظهار/إخفاء أي عنصر منها. القيم متخزنة في جدول _scfg (key/value) الموجود
أصلاً، وبتتقرأ بكاش بسيط في الذاكرة (TTL قصير) عشان منعملش استعلام قاعدة
بيانات مع كل عنصر في كل صفحة.
"""
import json
import time

from models import SessionLocal, _SysCfg

_CACHE_TTL = 10  # ثانية
_cache = {"orientation": None, "hidden": None, "ts": 0}


def _load():
    now = time.time()
    if _cache["ts"] and (now - _cache["ts"]) < _CACHE_TTL:
        return
    db = SessionLocal()
    try:
        orient_row = db.query(_SysCfg).filter(_SysCfg.k == "menu_orientation").first()
        hidden_row = db.query(_SysCfg).filter(_SysCfg.k == "hidden_menu_items").first()
        _cache["orientation"] = (orient_row.v if orient_row and orient_row.v else "vertical")
        try:
            _cache["hidden"] = set(json.loads(hidden_row.v)) if hidden_row and hidden_row.v else set()
        except (ValueError, TypeError):
            _cache["hidden"] = set()
        _cache["ts"] = now
    finally:
        db.close()


def get_menu_orientation() -> str:
    _load()
    return _cache["orientation"] or "vertical"


def get_hidden_menu_items() -> set:
    _load()
    return _cache["hidden"] or set()


def is_menu_visible(key: str) -> bool:
    return key not in get_hidden_menu_items()


def _invalidate():
    _cache["ts"] = 0


def set_menu_orientation(value: str):
    if value not in ("vertical", "horizontal"):
        value = "vertical"
    db = SessionLocal()
    try:
        row = db.query(_SysCfg).filter(_SysCfg.k == "menu_orientation").first()
        if not row:
            row = _SysCfg(k="menu_orientation", v=value)
            db.add(row)
        else:
            row.v = value
        db.commit()
    finally:
        db.close()
    _invalidate()


def set_hidden_menu_items(keys: list):
    db = SessionLocal()
    try:
        row = db.query(_SysCfg).filter(_SysCfg.k == "hidden_menu_items").first()
        payload = json.dumps(sorted(set(keys)))
        if not row:
            row = _SysCfg(k="hidden_menu_items", v=payload)
            db.add(row)
        else:
            row.v = payload
        db.commit()
    finally:
        db.close()
    _invalidate()


# كل عنصر ممكن يتظبط ظهوره/اختفاؤه من شاشة الإعدادات، مع تسمية عربي/إنجليزي
# للعرض. المفاتيح دي لازم تتطابق مع القيمة اللي بتتبعت لـ is_menu_visible()
# جوه القائمة الجانبية (templates/base.html).
MENU_ITEMS_REGISTRY = [
    ("dashboard", "لوحة التحكم", "Dashboard"),
    ("reservations", "الحجوزات", "Reservations"),
    ("bookings", "الحجوزات (قديم)", "Bookings (legacy)"),
    ("hotels", "الفنادق", "Hotels"),
    ("customers", "العملاء", "Customers"),
    ("suppliers", "الموردين", "Suppliers"),
    ("collections", "التحصيلات", "Receipts"),
    ("treasury", "الخزنة", "Cash Management"),
    ("transfers", "التحويلات", "Transfers"),
    ("closing", "الجرد اليومي", "Daily Closing"),
    ("bank", "تسوية البنك", "Bank Reconciliation"),
    ("expenses", "المصروفات", "Expenses"),
    ("supplier_payments", "سداد الموردين", "Supplier Payments"),
    ("accounting", "الحسابات", "General Ledger"),
    ("reconcile", "مطابقة الأرصدة", "Reconciliation"),
    ("employees", "الموظفين", "Employees"),
    ("attendance", "الحضور والانصراف", "Attendance"),
    ("payroll", "الرواتب", "Payroll"),
    ("commission_policies", "سياسات العمولات", "Commission Policies"),
    ("departments", "الأقسام", "Departments"),
    ("reports", "التقارير", "Reports"),
    ("insights", "التحليلات الذكية", "Insights"),
    ("settings", "الإعدادات", "Settings"),
]
