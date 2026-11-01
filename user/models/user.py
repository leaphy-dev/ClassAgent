from django.db import models
from django.contrib.auth.models import AbstractUser

class UserRole(models.TextChoices):
    GUEST = 'GUEST'
    STUDENT = 'STUDENT'
    TEACHER = 'TEACHER'
    ADMIN = 'ADMIN'

class User(AbstractUser):
    """
    基础用户模型
    """
    role = models.CharField(
        max_length=16,
        choices=UserRole.choices,
        default=UserRole.STUDENT,
        verbose_name="UserRole"
    )
    class_name = models.CharField(max_length=50, blank=True, null=True, verbose_name="Class")
    student_id = models.CharField(max_length=10, blank=True, null=True, verbose_name="ID")
