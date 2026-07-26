"""
سياق عام يحمل المستخدم الحالي للـ request الجاري، يُستخدم من auth.py (للتعيين)
ومن models.py (للقراءة عند تسجيل سجل التتبع Audit Log) بدون استيراد دائري.
"""
import contextvars

current_user_var: contextvars.ContextVar = contextvars.ContextVar("current_user", default=None)
