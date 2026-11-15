"""用 Django 内置信号记录登录/登出，无需改动 user 应用的视图。"""

from django.contrib.auth import user_logged_in, user_logged_out
from django.dispatch import receiver

from .models import AuditLog, record


@receiver(user_logged_in)
def on_login(sender, request, user, **kwargs):
    record(actor=user, action="用户登录", category=AuditLog.Category.AUTH,
           target=user.user_id, request=request)


@receiver(user_logged_out)
def on_logout(sender, request, user, **kwargs):
    record(actor=user, action="用户登出", category=AuditLog.Category.AUTH,
           target=getattr(user, "user_id", ""), request=request)
