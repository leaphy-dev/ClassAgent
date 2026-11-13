from django.conf import settings
from django.db import models

from user.models.enum import UserRole

from .classroom import ClassRoom


class Enrollment(models.Model):
    """Student <-> class room. One row = one student in one class. Remove = delete row."""

    classroom = models.ForeignKey(
        ClassRoom,
        on_delete=models.CASCADE,
        related_name="enrollments",
        verbose_name="class room",
    )
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="enrollments",
        verbose_name="student",
        limit_choices_to={"role": UserRole.STUDENT},
    )
    created_at = models.DateTimeField("created at", auto_now_add=True)

    class Meta:
        verbose_name = "enrollment"
        verbose_name_plural = "enrollments"
        constraints = [
            models.UniqueConstraint(
                fields=["classroom", "student"],
                name="uniq_enrollment_classroom_student",
            )
        ]

    def __str__(self) -> str:
        return f"{self.classroom.serial} - {self.student}"