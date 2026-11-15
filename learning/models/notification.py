from django.conf import settings
from django.db import models


class Notification(models.Model):
    """站内通知：作业发布、批改完成、系统消息。"""

    class Kind(models.TextChoices):
        ASSIGNMENT = "ASSIGNMENT", "作业通知"
        FEEDBACK = "FEEDBACK", "批改通知"
        SYSTEM = "SYSTEM", "系统消息"

    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
        verbose_name="接收人",
    )
    kind = models.CharField("类型", max_length=16, choices=Kind.choices, default=Kind.SYSTEM)
    title = models.CharField("标题", max_length=128)
    body = models.TextField("内容", blank=True)
    is_read = models.BooleanField("已读", default=False)
    created_at = models.DateTimeField("创建时间", auto_now_add=True)

    class Meta:
        verbose_name = "通知"
        verbose_name_plural = "通知"
        ordering = ["-created_at", "-id"]

    def __str__(self) -> str:
        return f"{self.recipient} · {self.title}"
