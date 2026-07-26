#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
backfill_journal_party_tags.py
===============================
إصلاح لمرة واحدة (one-time) لكل قيود اليومية القديمة اللي اتعملت قبل تصحيح
AccountingService.post(): كانت أسطر الذمم المدينة/الدائنة (AR/AP) بتتسجل
من غير ربط بالعميل أو المورد (customer_id / supplier_id فاضيين)، وده كان
معناه إن sync_supplier_cache() و sync_customer_cache() بيرجّعوا كل أرصدة
العملاء والموردين صفر مع أي عملية مالية جديدة في أي شاشة بالبرنامج.

السكريبت ده بيمر على القيود القديمة حسب مصدرها (source_type) ويربط سطر
AR/AP بصاحبه الصحيح، بعدين يعيد حساب كل الأرصدة من الآخر.

الاستخدام:
    python backfill_journal_party_tags.py            # تشغيل فعلي
    python backfill_journal_party_tags.py --dry-run   # عرض العدد اللي هيتصلح من غير حفظ
"""
import argparse
import sys
from models import (
    SessionLocal, JournalEntry, JournalLine, Account,
    Reservation, SupplierPayment, Collection,
)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    db = SessionLocal()
    fixed = 0
    try:
        ap = db.query(Account).filter(Account.key == "ap").first()
        ar = db.query(Account).filter(Account.key == "ar").first()
        if not ap or not ar:
            print("❌ حسابات AP/AR غير موجودة — شغّل seed_chart_of_accounts الأول")
            sys.exit(1)

        # 1) قيود الحجوزات (تكلفة = AP لمورد الفندق، إيراد = AR للعميل)
        for entry in db.query(JournalEntry).filter(JournalEntry.source_type == "reservation"):
            r = db.query(Reservation).get(entry.source_id)
            if not r:
                continue
            supplier_id = r.hotel.supplier_id if r.hotel else None
            for line in entry.lines:
                if line.account_id == ap.id and not line.supplier_id and supplier_id:
                    line.supplier_id = supplier_id
                    line.reservation_id = line.reservation_id or r.id
                    fixed += 1
                elif line.account_id == ar.id and not line.customer_id and r.customer_id:
                    line.customer_id = r.customer_id
                    line.reservation_id = line.reservation_id or r.id
                    fixed += 1

        # 2) دفعات الموردين
        for entry in db.query(JournalEntry).filter(JournalEntry.source_type == "supplier_payment"):
            p = db.query(SupplierPayment).get(entry.source_id)
            if not p or not p.supplier_id:
                continue
            for line in entry.lines:
                if line.account_id == ap.id and not line.supplier_id:
                    line.supplier_id = p.supplier_id
                    fixed += 1

        # 3) التحصيلات
        for entry in db.query(JournalEntry).filter(JournalEntry.source_type == "collection"):
            c = db.query(Collection).get(entry.source_id)
            if not c or not getattr(c, "customer_id", None):
                continue
            for line in entry.lines:
                if line.account_id == ar.id and not line.customer_id:
                    line.customer_id = c.customer_id
                    fixed += 1

        # 4) عمولات المورد التشغيلي (ops_supplier) فقط — دي الوحيدة من نوع العمولات
        #    اللي بتمثل مديونية حقيقية على مورد فعلي، باقي الأنواع (موظف/وكيل) تفضل
        #    من غير ربط لأنها مش على كيان "مورد" أصلاً.
        for entry in db.query(JournalEntry).filter(
            JournalEntry.source_type == "commission",
            JournalEntry.description.like("%ops_supplier%"),
        ):
            r = db.query(Reservation).get(entry.source_id)
            if not r or not r.ops_supplier_id:
                continue
            for line in entry.lines:
                if line.account_id == ap.id and not line.supplier_id:
                    line.supplier_id = r.ops_supplier_id
                    line.reservation_id = line.reservation_id or r.id
                    fixed += 1

        print(f"سطور هتتصلح: {fixed}")

        if args.dry_run:
            print("dry-run — مفيش حفظ")
            db.rollback()
            return

        from services.accounting_service import AccountingService
        AccountingService(db).sync_all_caches()
        db.commit()
        print("✅ تم الإصلاح وإعادة حساب كل أرصدة العملاء والموردين.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
