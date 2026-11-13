from django.conf import settings
from django.db import models


class ClassRoom(models.Model):
    """Teaching class. Subject and term are columns on this table."""

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