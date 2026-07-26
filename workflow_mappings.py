"""Mapping from service types / reservation features to default workflow tasks."""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class TaskDef:
    title_ar: str
    title_en: str
    priority: str = "normal"  # low / normal / high / urgent
    reminder: int = 24        # hours before due_date
    due_days_from_checkin: int = 0       # days before checkin (negative = after)
    due_days_from_now: Optional[int] = None  # fixed days from creation


# Each key matches a Service name (case-insensitive contains)
SERVICE_TASKS = {
    "فندق": [
        TaskDef("تأكيد حجز الفندق", "Confirm Hotel Booking", "high", 48, -3),
        TaskDef("دفع العربون للفندق", "Pay Hotel Deposit", "high", 48, -1),
    ],
    "Hotel": [
        TaskDef("Confirm Hotel Booking", "Confirm Hotel Booking", "high", 48, -3),
        TaskDef("Pay Hotel Deposit", "Pay Hotel Deposit", "high", 48, -1),
    ],
    "تذكرة": [
        TaskDef("إصدار التذكرة", "Issue Ticket", "high", 72, -5),
        TaskDef("تأكيد الحجز الجوي", "Confirm Flight Booking", "high", 72, -7),
    ],
    "Ticket": [
        TaskDef("Issue Ticket", "Issue Ticket", "high", 72, -5),
        TaskDef("Confirm Flight Booking", "Confirm Flight Booking", "high", 72, -7),
    ],
    "فيزا": [
        TaskDef("طلب التأشيرة", "Apply for Visa", "urgent", 48, -14),
        TaskDef("متابعة التأشيرة", "Follow up Visa", "high", 48, -7),
    ],
    "Visa": [
        TaskDef("Apply for Visa", "Apply for Visa", "urgent", 48, -14),
        TaskDef("Follow up Visa", "Follow up Visa", "high", 48, -7),
    ],
    "تأمين": [
        TaskDef("إصدار وثيقة التأمين", "Issue Insurance Policy", "normal", 24, -3),
    ],
    "Insurance": [
        TaskDef("Issue Insurance Policy", "Issue Insurance Policy", "normal", 24, -3),
    ],
    "نقل": [
        TaskDef("تأكيد النقل", "Confirm Transport", "high", 24, -1),
        TaskDef("تجهيز مركبة الاستقبال", "Arrange Pickup Vehicle", "normal", 12, -1),
    ],
    "Transport": [
        TaskDef("Confirm Transport", "Confirm Transport", "high", 24, -1),
        TaskDef("Arrange Pickup Vehicle", "Arrange Pickup Vehicle", "normal", 12, -1),
    ],
}


# Default tasks for EVERY confirmed reservation (regardless of services)
DEFAULT_TASKS = [
    TaskDef("إصدار Voucher", "Issue Voucher", "high", 48, -2),
    TaskDef("إخطار الشرطة", "Police Notification", "high", 48, -1),
    TaskDef("إرسال برنامج الرحلة للعميل", "Send Itinerary to Customer", "normal", 24, -2),
    TaskDef("متابعة الوصول", "Check-in Follow up", "normal", 12, 0),
    TaskDef("إغلاق الحجز", "Close Reservation", "normal", 24, 1),
]


def get_tasks_for_reservation(reservation, db):
    """Return list of (TaskDef, service_name) derived from reservation services."""
    tasks = []
    seen = set()
    for svc in reservation.services:
        svc_name = svc.name if hasattr(svc, "name") else ""
        for key, svc_tasks in SERVICE_TASKS.items():
            if key.lower() in svc_name.lower():
                for t in svc_tasks:
                    dedup = (t.title_ar, t.title_en)
                    if dedup not in seen:
                        seen.add(dedup)
                        tasks.append((t, svc_name))
    # Add default tasks
    for t in DEFAULT_TASKS:
        dedup = (t.title_ar, t.title_en)
        if dedup not in seen:
            seen.add(dedup)
            tasks.append((t, ""))
    return tasks
