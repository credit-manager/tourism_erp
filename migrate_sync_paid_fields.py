"""
تصحيح paid_to_office / paid_to_hotel لجميع الحجوزات من التوزيعات الفعلية.
تشغيل: python migrate_sync_paid_fields.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from models import SessionLocal, Reservation
from services.reconciliation_service import ReconciliationService


def run():
    db = SessionLocal()
    try:
        total = db.query(Reservation).count()
        fixed = 0
        for r in db.query(Reservation).all():
            old_office = r.paid_to_office
            old_hotel = r.paid_to_hotel
            ReconciliationService.sync_reservation_paid_fields(db, r)
            if r.paid_to_office != old_office or r.paid_to_hotel != old_hotel:
                fixed += 1
                print(f"  {r.booking_number}: office {old_office} → {r.paid_to_office}, hotel {old_hotel} → {r.paid_to_hotel}")
        db.commit()
        print(f"\nتم: {total} حجز، تعديل {fixed} حجز")
    finally:
        db.close()


if __name__ == "__main__":
    run()
