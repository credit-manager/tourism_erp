"""Build a unified timeline for a reservation."""

from datetime import datetime, date


def build_reservation_timeline(db, reservation_id):
    """Query all sources and return a merged list of timeline dicts sorted by timestamp descending."""
    from models import (
        Reservation, StateLog, AuditLog, CustomerTimeline,
        CollectionAllocation, Collection,
        SupplierPaymentAllocation, SupplierPayment,
        ReservationDocument,
    )

    items = []

    # 1. Reservation creation
    r = db.query(Reservation).get(reservation_id)
    if r and r.created_date:
        ts = datetime.combine(r.created_date, datetime.min.time())
        items.append({
            "ts": ts, "type": "created", "user": "",
            "desc_ar": "تم إنشاء الحجز", "desc_en": "Reservation created",
            "link": None,
        })

    # 2. StateLog — state transitions
    for log in db.query(StateLog).filter(
        StateLog.reservation_id == reservation_id
    ).order_by(StateLog.timestamp.asc()).all():
        items.append({
            "ts": log.timestamp or ts,
            "type": "state_change",
            "user": log.username or "",
            "desc_ar": f"تغيير الحالة من {log.from_state} إلى {log.to_state} — {log.transition}",
            "desc_en": f"Status changed from {log.from_state} to {log.to_state} — {log.transition}",
            "link": None,
            "reason": log.reason,
        })

    # 3. AuditLog — edits on reservations table
    for al in db.query(AuditLog).filter(
        AuditLog.table_name == "reservations",
        AuditLog.record_id == reservation_id,
    ).order_by(AuditLog.timestamp.asc()).all():
        action_map_ar = {"create": "إنشاء", "update": "تعديل", "delete": "حذف"}
        action_map_en = {"create": "Create", "update": "Update", "delete": "Delete"}
        items.append({
            "ts": al.timestamp,
            "type": "edit",
            "user": al.username or "",
            "desc_ar": f"{action_map_ar.get(al.action, al.action)} — {al.summary or ''}",
            "desc_en": f"{action_map_en.get(al.action, al.action)} — {al.summary or ''}",
            "link": None,
        })

    # 4. CustomerTimeline — events linked to this reservation
    for ct in db.query(CustomerTimeline).filter(
        CustomerTimeline.reference_type == "reservation",
        CustomerTimeline.reference_id == reservation_id,
    ).order_by(CustomerTimeline.created_at.asc()).all():
        type_labels_ar = {"note": "ملاحظة", "call": "مكالمة", "email": "بريد", "meeting": "اجتماع",
                          "reservation": "حجز", "collection": "تحصيل", "quote": "عرض سعر",
                          "task": "مهمة", "complaint": "شكوى", "system": "نظام"}
        type_labels_en = {"note": "Note", "call": "Call", "email": "Email", "meeting": "Meeting",
                          "reservation": "Reservation", "collection": "Collection", "quote": "Quote",
                          "task": "Task", "complaint": "Complaint", "system": "System"}
        lbl_ar = type_labels_ar.get(ct.type, ct.type)
        lbl_en = type_labels_en.get(ct.type, ct.type)
        items.append({
            "ts": ct.created_at,
            "type": ct.type,
            "user": ct.created_by or "",
            "desc_ar": f"{lbl_ar}: {ct.content or ''}",
            "desc_en": f"{lbl_en}: {ct.content or ''}",
            "link": None,
        })

    # 5. CollectionAllocation — payments collected toward this reservation
    for ca in db.query(CollectionAllocation).filter(
        CollectionAllocation.reservation_id == reservation_id
    ).order_by(CollectionAllocation.date.asc()).all():
        coll = db.query(Collection).get(ca.collection_id) if ca.collection_id else None
        ts = datetime.combine(ca.date or date.today(), datetime.min.time()) if ca.date else datetime.min
        ref = coll.collection_number if coll else f"#{ca.collection_id}"
        link = f"/collections/{ca.collection_id}/edit" if coll else None
        items.append({
            "ts": ts,
            "type": "payment",
            "user": coll.created_by if coll else "",
            "desc_ar": f"تحصيل مبلغ {ca.amount} — سند {ref}",
            "desc_en": f"Collection of {ca.amount} — Receipt {ref}",
            "link": link,
        })

    # 6. SupplierPaymentAllocation — payments to supplier for this reservation
    for spa in db.query(SupplierPaymentAllocation).filter(
        SupplierPaymentAllocation.reservation_id == reservation_id
    ).order_by(SupplierPaymentAllocation.date.asc()).all():
        sp = db.query(SupplierPayment).get(spa.payment_id) if spa.payment_id else None
        ts = datetime.combine(spa.date or date.today(), datetime.min.time()) if spa.date else datetime.min
        ref = sp.payment_number if sp else f"#{spa.payment_id}"
        link = f"/supplier-payments/{spa.payment_id}/edit" if sp else None
        items.append({
            "ts": ts,
            "type": "supplier_payment",
            "user": sp.created_by if sp else "",
            "desc_ar": f"دفع للمورد مبلغ {spa.amount} — سند {ref}",
            "desc_en": f"Supplier payment of {spa.amount} — Voucher {ref}",
            "link": link,
        })

    # 7. ReservationDocument — uploaded documents
    for doc in db.query(ReservationDocument).filter(
        ReservationDocument.reservation_id == reservation_id
    ).order_by(ReservationDocument.uploaded_at.asc()).all():
        ts = datetime.combine(doc.uploaded_at or date.today(), datetime.min.time())
        doc_type_ar = {"passport": "جواز سفر", "voucher": "قسيمة", "invoice": "فاتورة",
                       "contract": "عقد", "image": "صورة", "other": "مستند"}
        dt_ar = doc_type_ar.get(doc.doc_type, doc.doc_type)
        items.append({
            "ts": ts,
            "type": "document",
            "user": "",
            "desc_ar": f"رفع {dt_ar}: {doc.original_name or ''}",
            "desc_en": f"Uploaded {doc.doc_type}: {doc.original_name or ''}",
            "link": f"/uploads/{doc.file_path}" if doc.file_path else None,
        })

    # Sort descending by timestamp, then by type for determinism
    items.sort(key=lambda x: (x["ts"], x["type"]), reverse=True)
    return items
