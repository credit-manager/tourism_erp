"""State Machine for Reservation lifecycle."""

from dataclasses import dataclass, field
from typing import Callable, Optional
from models import Reservation, StateLog

# ─── States ──────────────────────────────────────────────
DRAFT = "draft"
QUOTED = "quoted"
PENDING_APPROVAL = "pending_approval"
CONFIRMED = "confirmed"
IN_SERVICE = "in_service"
COMPLETED = "completed"
CANCELLED = "cancelled"

STATES = [DRAFT, QUOTED, PENDING_APPROVAL, CONFIRMED, IN_SERVICE, COMPLETED, CANCELLED]

STATE_LABELS_AR = {
    DRAFT: "مسودة",
    QUOTED: "تم عرض السعر",
    PENDING_APPROVAL: "بانتظار الموافقة",
    CONFIRMED: "مؤكد",
    IN_SERVICE: "قيد التنفيذ",
    COMPLETED: "مكتمل",
    CANCELLED: "ملغي",
}

STATE_LABELS_EN = {
    DRAFT: "Draft",
    QUOTED: "Quoted",
    PENDING_APPROVAL: "Pending Approval",
    CONFIRMED: "Confirmed",
    IN_SERVICE: "In Service",
    COMPLETED: "Completed",
    CANCELLED: "Cancelled",
}

STATE_COLORS = {
    DRAFT: "neutral",
    QUOTED: "info",
    PENDING_APPROVAL: "warning",
    CONFIRMED: "success",
    IN_SERVICE: "primary",
    COMPLETED: "success",
    CANCELLED: "danger",
}

# ─── Transition Definition ───────────────────────────────

@dataclass
class Transition:
    from_state: str
    to_state: str
    label_ar: str
    label_en: str
    permission: str  # permission key required
    condition: Optional[Callable] = None  # (reservation, db) -> (ok: bool, msg: str)
    require_reason: bool = False
    require_cancellation_fee: bool = False


def _has_price(r):
    """Condition: reservation must have a company_cost > 0."""
    return (r.company_cost or 0) > 0


def _has_hotel_or_supplier(r):
    """Condition: reservation must have a hotel or supplier assigned."""
    return bool(r.hotel_id or r.ops_supplier_id)


def _not_cancelled(r):
    return r.status != CANCELLED


def _is_paid(r):
    return (r.paid_to_office or 0) >= (r.company_cost or 0)


# ─── Transition Graph ────────────────────────────────────

TRANSITIONS = [
    # Draft → Quoted (need a price)
    Transition(DRAFT, QUOTED, "عرض السعر", "Quote", "reservations.edit",
               condition=lambda r, db: (
                   (True, "") if _has_price(r)
                   else (False, "يجب إضافة سعر البيع قبل عرض السعر / Must set a selling price before quoting")
               )),
    # Draft → Cancelled
    Transition(DRAFT, CANCELLED, "إلغاء", "Cancel", "reservations.delete",
               require_reason=True),

    # Quoted → Pending Approval
    Transition(QUOTED, PENDING_APPROVAL, "طلب موافقة العميل", "Request Approval", "reservations.edit"),
    # Quoted → Draft (revise)
    Transition(QUOTED, DRAFT, "مراجعة العرض", "Revise Quote", "reservations.edit"),
    # Quoted → Cancelled
    Transition(QUOTED, CANCELLED, "إلغاء", "Cancel", "reservations.delete",
               require_reason=True),

    # Pending Approval → Confirmed (need price + hotel/supplier + credit check)
    Transition(PENDING_APPROVAL, CONFIRMED, "تأكيد الحجز", "Confirm", "reservations.confirm",
               condition=lambda r, db: _confirm_conditions(r, db)),
    # Pending Approval → Quoted (reject)
    Transition(PENDING_APPROVAL, QUOTED, "رفض ومراجعة", "Reject & Revise", "reservations.edit",
               require_reason=True),
    # Pending Approval → Cancelled
    Transition(PENDING_APPROVAL, CANCELLED, "إلغاء", "Cancel", "reservations.delete",
               require_reason=True),

    # Confirmed → In Service
    Transition(CONFIRMED, IN_SERVICE, "بدء الخدمة", "Start Service", "reservations.edit"),
    # Confirmed → Cancelled
    Transition(CONFIRMED, CANCELLED, "إلغاء", "Cancel", "reservations.delete",
               require_reason=True, require_cancellation_fee=True),

    # In Service → Completed
    Transition(IN_SERVICE, COMPLETED, "إكمال", "Complete", "reservations.edit",
               condition=lambda r, db: (
                   (True, "") if (r.paid_to_office or 0) >= (r.company_cost or 0)
                   or not _has_price(r)
                   else (False, "يجب تسوية المدفوعات قبل الإكمال / Payments must be settled before completion")
               )),
    # In Service → Cancelled
    Transition(IN_SERVICE, CANCELLED, "إلغاء", "Cancel", "reservations.delete",
               require_reason=True, require_cancellation_fee=True),

    # Completed → (terminal)
    # Cancelled → (terminal)
]


def _confirm_conditions(r, db):
    """Combined conditions for confirming a reservation."""
    from routers import _check_credit_limit
    from decimal import Decimal
    issues = []
    if not _has_price(r):
        issues.append("يجب تحديد سعر البيع قبل التأكيد / Set selling price before confirming")
    if not _has_hotel_or_supplier(r):
        issues.append("يجب تحديد الفندق أو المورد قبل التأكيد / Set hotel or supplier before confirming")
    if r.reservation_type == "credit" and r.customer_id:
        net = max((r.company_cost or 0) - (r.paid_to_office or 0), Decimal("0"))
        ok, msg, _ = _check_credit_limit(db, r.customer_id, net)
        if not ok:
            issues.append(msg)
    if issues:
        return (False, " | ".join(issues))
    return (True, "")


def allowed_transitions(reservation):
    """Return list of Transition objects allowed from current state."""
    return [t for t in TRANSITIONS if t.from_state == reservation.status]


def can_transition(reservation, to_state, db):
    """Check if transition to to_state is allowed. Returns (ok: bool, msg: str)."""
    for t in TRANSITIONS:
        if t.from_state == reservation.status and t.to_state == to_state:
            if t.condition:
                return t.condition(reservation, db)
            return (True, "")
    return (False, f"الانتقال من {reservation.status} إلى {to_state} غير مسموح / Transition not allowed")


def apply_transition(reservation, to_state, db, user, reason="", data=None):
    """Execute a state transition with full validation and logging.
    Returns (ok: bool, msg: str).
    """
    from datetime import datetime

    # Find matching transition
    trans = None
    for t in TRANSITIONS:
        if t.from_state == reservation.status and t.to_state == to_state:
            trans = t
            break
    if not trans:
        return (False, f"الانتقال من {reservation.status} إلى {to_state} غير مسموح")

    # Check condition
    if trans.condition:
        ok, msg = trans.condition(reservation, db)
        if not ok:
            return (False, msg)

    # Check reason requirement
    if trans.require_reason and not reason.strip():
        return (False, "يجب إدخال سبب الإلغاء / Cancellation reason is required")

    # Execute
    old_status = reservation.status
    reservation.status = to_state

    if to_state == CANCELLED:
        reservation.cancelled_at = datetime.utcnow()
        reservation.cancelled_by = getattr(user, "username", "?")
        reservation.cancellation_reason = reason

    # Log
    log = StateLog(
        reservation_id=reservation.id,
        from_state=old_status,
        to_state=to_state,
        transition=trans.label_ar if getattr(user, 'lang', 'ar') == 'ar' else trans.label_en,
        user_id=getattr(user, "id", 0),
        username=getattr(user, "username", "?"),
        reason=reason,
    )
    db.add(log)

    # Auto-create workflow tasks when confirming
    if to_state == CONFIRMED:
        from workflow_mappings import get_tasks_for_reservation
        from models import WorkflowTask, Service
        task_defs = get_tasks_for_reservation(reservation, db)
        existing_titles = set()
        for wt in db.query(WorkflowTask).filter(
            WorkflowTask.reservation_id == reservation.id
        ).all():
            existing_titles.add(wt.title)
        for td, svc_name in task_defs:
            if td.title_ar in existing_titles or td.title_en in existing_titles:
                continue
            due = None
            if td.due_days_from_now is not None:
                from datetime import timedelta
                due = datetime.utcnow().date() + timedelta(days=td.due_days_from_now)
            elif reservation.checkin_date and td.due_days_from_checkin:
                from datetime import timedelta
                due = reservation.checkin_date + timedelta(days=td.due_days_from_checkin)
            db.add(WorkflowTask(
                reservation_id=reservation.id,
                title=td.title_ar,
                description=f"{td.title_en} | {svc_name}" if svc_name else td.title_en,
                priority=td.priority,
                reminder=td.reminder,
                due_date=due,
            ))

    db.commit()
    return (True, "")


def migrate_status(status):
    """Map old status values to new state machine states."""
    mapping = {
        "draft": DRAFT,
        "pending": PENDING_APPROVAL,
        "confirmed": CONFIRMED,
        "checked_in": IN_SERVICE,
        "checked_out": COMPLETED,
        "cancelled": CANCELLED,
        "closed": COMPLETED,
    }
    return mapping.get(status, DRAFT)
