import datetime

WORKFLOW_STATES = ["draft", "reviewed", "approved", "posted", "cancelled"]
VALID_TRANSITIONS = {
    "draft":     ["reviewed", "cancelled"],
    "reviewed":  ["approved", "draft", "cancelled"],
    "approved":  ["posted", "cancelled"],
    "posted":    ["cancelled"],
    "cancelled": [],
}


class WorkflowError(ValueError):
    pass


class WorkflowService:
    """إدارة دورة حياة المستندات المالية."""

    def __init__(self, db):
        self.db = db

    @staticmethod
    def validate_transition(doc, new_status):
        current = doc.status or "draft"
        allowed = VALID_TRANSITIONS.get(current, [])
        if new_status not in allowed:
            raise WorkflowError(
                f"لا يمكن الانتقال من {current} إلى {new_status}. "
                f"المسموح: {', '.join(allowed)}"
            )

    def submit(self, doc, user):
        """draft → reviewed: تقديم للمراجعة."""
        self.validate_transition(doc, "reviewed")
        doc.status = "reviewed"
        doc.reviewed_at = datetime.datetime.utcnow()
        doc.reviewed_by = getattr(user, "username", "?")

    def review(self, doc, user, approved=True):
        """reviewed → approved (مقبول) / draft (مرفوض)."""
        if approved:
            self.validate_transition(doc, "approved")
            doc.status = "approved"
            doc.approved_at = datetime.datetime.utcnow()
            doc.approved_by = getattr(user, "username", "?")
        else:
            self.validate_transition(doc, "draft")
            doc.status = "draft"
            doc.reviewed_at = None
            doc.reviewed_by = None

    def approve(self, doc, user):
        """approved → posted: اعتماد وترحيل (يؤثر على الخزنة والأستاذ)."""
        self.validate_transition(doc, "posted")
        doc.status = "posted"
        doc.posted_at = datetime.datetime.utcnow()
        doc.posted_by = getattr(user, "username", "?")

    def post(self, doc, user):
        """نفس approve — للتوافق."""
        self.approve(doc, user)

    def cancel(self, doc, user, reason=""):
        """أي حالة → cancelled."""
        self.validate_transition(doc, "cancelled")
        doc.status = "cancelled"
        doc.cancelled_at = datetime.datetime.utcnow()
        doc.cancelled_by = getattr(user, "username", "?")
        doc.cancellation_reason = reason or ""

    def correct(self, doc, user, reversal_cls, reversal_data_fn):
        """لمستند posted: ينشئ قيد عكسي + مستند جديد draft.
        
        reversal_cls: كلاس المستند الجديد (مثلاً Collection)
        reversal_data_fn: دالة(doc) → dict ببيانات المستند المعكوس
        """
        if doc.status != "posted":
            raise WorkflowError("التصحيح مسموح فقط للمستندات المرحّلة (posted).")

        from services.accounting_service import AccountingService
        acc = AccountingService(self.db)
        reversal_entry = acc.reverse_entry(doc, created_by=getattr(user, "username", "?"))

        new_doc = reversal_cls(**reversal_data_fn(doc))
        new_doc.status = "draft"
        new_doc.created_at = datetime.datetime.utcnow()
        new_doc.created_by = getattr(user, "username", "?")
        self.db.add(new_doc)
        self.db.flush()

        return new_doc, reversal_entry
