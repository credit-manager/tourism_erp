#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
factory_reset.py
=================
اعدادات ضبط المصنع لبرنامج tourism_erp.

بيمسح كل البيانات اللي اتضافت وانت بتستخدم البرنامج (حجوزات، عملاء، محاسبة،
موارد بشرية، بيانات مرجعية زي الفنادق والموردين... الخ) ويسيب بس:
  - جدول users (حسابات المستخدمين وصلاحياتهم)
  - alembic_version (رقم نسخة قاعدة البيانات - بيانات نظام مش بيانات استخدام)
  - _scfg (اعدادات نظام داخلية)

الاستخدام:
    python factory_reset.py                 # تشغيل عادي (بياخد باك أب تلقائي الأول)
    python factory_reset.py --db path.db    # تحديد مسار قاعدة بيانات مختلف
    python factory_reset.py --yes           # تخطي سؤال التأكيد (للتشغيل الآلي)

ملحوظة مهمة: السكريبت بياخد نسخة احتياطية (backup) تلقائية من القاعدة قبل
أي مسح، بمسمى فيه التاريخ والوقت، عشان لو حصل غلط تقدر ترجعلها.
"""
import argparse
import shutil
import sqlite3
import sys
from datetime import datetime

# الجداول اللي مش هتتمسح - بيانات النظام والحسابات
KEEP_TABLES = {"users", "alembic_version", "_scfg", "sqlite_sequence"}


def get_all_tables(cur):
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
    return [r[0] for r in cur.fetchall()]


def main():
    parser = argparse.ArgumentParser(description="ضبط المصنع لبرنامج tourism_erp")
    parser.add_argument("--db", default="tourism_erp.db", help="مسار ملف قاعدة البيانات")
    parser.add_argument("--yes", action="store_true", help="تنفيذ مباشرة من غير سؤال تأكيد")
    args = parser.parse_args()

    db_path = args.db

    # 1) باك أب تلقائي قبل أي حاجة
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = f"{db_path}.before_factory_reset_{stamp}.bak"
    try:
        shutil.copy2(db_path, backup_path)
    except FileNotFoundError:
        print(f"❌ مش لاقي قاعدة البيانات في المسار: {db_path}")
        sys.exit(1)
    print(f"✅ اتعمل باك أب قبل المسح: {backup_path}")

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("PRAGMA foreign_keys = OFF")

    all_tables = get_all_tables(cur)
    to_clear = [t for t in all_tables if t not in KEEP_TABLES]

    # عرض ملخص قبل التنفيذ
    print("\nالجداول اللي هتتمسح بالكامل:")
    counts_before = {}
    for t in to_clear:
        cur.execute(f'SELECT COUNT(*) FROM "{t}"')
        c = cur.fetchone()[0]
        counts_before[t] = c
        if c:
            print(f"  - {t}: {c} صف")

    print(f"\nالجداول اللي هتفضل زي ما هي: {', '.join(sorted(KEEP_TABLES - {'sqlite_sequence'}))}")

    if not args.yes:
        answer = input("\n⚠️  متأكد عايز تكمل؟ الإجراء ده مش هيتعمله رجوع إلا من الباك أب. اكتب 'تأكيد' وكمل: ")
        if answer.strip() != "تأكيد":
            print("تم الإلغاء. مفيش أي حاجة اتمسحت.")
            conn.close()
            return

    # 2) فك ربط users.employee_id قبل ما نمسح جدول employees (لتفادي أي مشكلة ربط)
    try:
        cur.execute("UPDATE users SET employee_id = NULL")
    except sqlite3.OperationalError:
        pass

    # 3) مسح كل الجداول المطلوبة
    for t in to_clear:
        cur.execute(f'DELETE FROM "{t}"')

    # 4) تصفير عدادات الـ auto increment للجداول اللي اتمسحت عشان الأرقام تبدأ من جديد (لو موجودة)
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='sqlite_sequence'")
    if cur.fetchone():
        for t in to_clear:
            cur.execute("DELETE FROM sqlite_sequence WHERE name = ?", (t,))

    conn.commit()
    cur.execute("VACUUM")
    conn.commit()
    conn.close()

    print("\n✅ تم ضبط المصنع بنجاح.")
    print(f"   حسابات المستخدمين والصلاحيات اتسابت زي ما هي.")
    print(f"   النسخة الاحتياطية القديمة محفوظة في: {backup_path}")


if __name__ == "__main__":
    main()
