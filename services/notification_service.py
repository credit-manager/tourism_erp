"""
NotificationService
====================
محرك إشعارات حقيقي: أي حدث في النظام (طلب إجازة، اعتماد دفعة، تحصيل جاهز
للترحيل...) بيولّد سجل إشعار فعلي في قاعدة البيانات لكل مستخدم مستهدف،
بدل ما يفضل مجرد استعلام لحظي بيختفي أثره أول ما تقفل الصفحة.
"""
import datetime
from models import Notification, User
import auth


class NotificationService:
    def __init__(self, db):
        self.db = db

    def notify_user(self, user_id: int, title: str, body: str = "", link: str = None, category: str = "info"):
        n = Notification(user_id=user_id, title=title, body=body, link=link, category=category)
        self.db.add(n)
        return n

    def notify_permission(self, permission_key: str, title: str, body: str = "",
                          link: str = None, category: str = "info", exclude_user_id: int = None):
        """يبعت إشعار لكل مستخدم عنده صلاحية معيّنة (زي كل اللي يقدروا يعتمدوا
        دفعة مورد) — بيحترم دور المستخدم + أي override شخصي (extra/revoked)
        عن طريق auth.has_permission نفسها، بدون تكرار منطق الصلاحيات هنا."""
        users = self.db.query(User).filter(User.is_active == 1).all()
        sent = []
        for u in users:
            if exclude_user_id and u.id == exclude_user_id:
                continue
            if auth.has_permission(u, permission_key):
                sent.append(self.notify_user(u.id, title, body, link, category))
        return sent

    def notify_employee_user(self, employee_id: int, title: str, body: str = "",
                             link: str = None, category: str = "info"):
        """يبعت إشعار لحساب المستخدم المرتبط بموظف معيّن (لو عنده حساب دخول أصلاً)."""
        u = self.db.query(User).filter(User.employee_id == employee_id).first()
        if u:
            return self.notify_user(u.id, title, body, link, category)
        return None

    def unread_count(self, user_id: int) -> int:
        return self.db.query(Notification).filter(
            Notification.user_id == user_id, Notification.is_read == 0
        ).count()

    def list_for_user(self, user_id: int, limit: int = 20, unread_only: bool = False):
        q = self.db.query(Notification).filter(Notification.user_id == user_id)
        if unread_only:
            q = q.filter(Notification.is_read == 0)
        return q.order_by(Notification.created_at.desc()).limit(limit).all()

    def mark_read(self, notification_id: int, user_id: int):
        n = self.db.query(Notification).filter(
            Notification.id == notification_id, Notification.user_id == user_id
        ).first()
        if n:
            n.is_read = 1
        return n

    def mark_all_read(self, user_id: int):
        self.db.query(Notification).filter(
            Notification.user_id == user_id, Notification.is_read == 0
        ).update({"is_read": 1})
