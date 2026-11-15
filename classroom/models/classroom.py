from django.conf import settings
from django.db import models


class ClassRoom(models.Model):
    """Teaching class. A course is the top-level unit; a class belongs to one course."""

    course = models.ForeignKey(
        "course.Course",
        on_delete=models.PROTECT,
        related_name="classrooms",
        verbose_name="所属课程",
        null=True,
        blank=True,
        help_text="过渡期允许为空，便于兼容已有数据；新数据应由种子脚本或后台统一填充。",
    )
    serial = models.CharField(
        "serial",
        max_length=32,
        unique=True,
        help_text="Class serial, like a student ID.",
    )
    subject = models.CharField("subject", max_length=32)
    term = models.CharField("term", max_length=32)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_classrooms",
        verbose_name="created by",
    )
    created_at = models.DateTimeField("created at", auto_now_add=True)
    updated_at = models.DateTimeField("updated at", auto_now=True)

    class Meta:
        verbose_name = "class room"
        verbose_name_plural = "class rooms"

    def __str__(self) -> str:
        return f"{self.serial} ({self.subject}, {self.term})"