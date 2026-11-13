from django.conf import settings
from django.db import models

from user.models.enum import UserRole

from .classroom import ClassRoom


class Teaching(models.Model):
    """Teacher <-> class room. One row = one teacher teaches one class. Remove = delete row."""

    classroom = models.ForeignKey(
        ClassRoom,
        on_delete=models.CASCADE,
        related_name="teachings",
        verbose_name="class room",
    )
    teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="teachings",
        verbose_name="teacher",
        limit_choices_to={"role": UserRole.TEACHER},
    )
    created_at = models.DateTimeField("created at", auto_now_add=True)

    class Meta:
        verbose_name = "teaching"
        verbose_name_plural = "teachings"
        constraints = [
            models.UniqueConstraint(
                fields=["classroom", "teacher"],
                name="uniq_teaching_classroom_teacher",
            )
        ]

    def __str__(self) -> str:
        return f"{self.classroom.serial} - {self.teacher}"