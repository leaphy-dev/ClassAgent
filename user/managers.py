# user/managers.py
from django.contrib.auth.models import BaseUserManager

from .models.enum import UserRole


class UserManager(BaseUserManager):
    def create_user(self, user_id, email=None, password=None, **extra_fields):
        if not user_id:
            raise ValueError('User ID cannot be empty!')
        if email:
            email = self.normalize_email(email)
        user = self.model(user_id=user_id, email=email, **extra_fields)
        user.set_password(password)
        user.save()
        return user

    def create_superuser(self, user_id, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)

        if not extra_fields.get('is_staff'):
            raise ValueError()
        if not extra_fields.get('is_superuser'):
            raise ValueError()

        extra_fields.setdefault('role', UserRole.ADMIN) # 记得配置为ADMIN
        return self.create_user(user_id, email, password, **extra_fields)