from django.db import models

class UserRole(models.TextChoices):
    GUEST = 'GUEST'
    STUDENT = 'STUDENT'
    TEACHER = 'TEACHER'
    ADMIN = 'ADMIN'