"""إنشاء جدول notifications (محرك الإشعارات)"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from models import engine, Notification

Notification.__table__.create(bind=engine, checkfirst=True)
print("  + جدول notifications جاهز")
print("Done.")
