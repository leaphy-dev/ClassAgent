from django.db import models
from django.contrib.auth.models import AbstractUser

from ..managers import UserManager

class UserRole(models.TextChoices):
    GUEST = 'GUEST'
    STUDENT = 'STUDENT'
    TEACHER = 'TEACHER'
    ADMIN = 'ADMIN'

class User(AbstractUser):
    """
    基础用户模型
    """
    user_id = models.CharField(
        max_length=10,
        blank=True,
        null=False,
        unique=True,
        verbose_name="ID"
    )

    role = models.CharField(
        max_length=16,
        choices=UserRole.choices,
        default=UserRole.STUDENT,
        verbose_name="UserRole"
    )

    USERNAME_FIELD = "user_id"
    REQUIRED_FIELDS = ["email"]

    objects = UserManager()

    def is_admin(self) -> bool:
        return self.role == UserRole.ADMIN

    def is_teacher(self) -> bool:
        return self.role == UserRole.TEACHER

    def is_student(self) -> bool:
        return self.role == UserRole.STUDENT

    def display_name(self) -> str:
        return self.get_full_name() or self.user_id
