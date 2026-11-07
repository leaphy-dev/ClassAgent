from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models.user import User


@admin.register(User)
class UserManageAdmin(UserAdmin):

    list_display = ('username', 'email', 'role', 'user_id', 'is_staff', 'is_active')

    list_filter = ('role', 'is_staff', 'is_superuser', 'is_active')

    fieldsets = list(UserAdmin.fieldsets or []) + [
        ('业务信息', {'fields': ('role', 'user_id')} ),
    ]

    add_fieldsets = list(UserAdmin.add_fieldsets or []) + [
        ('业务信息', {'fields': ('role', 'user_id')} ),
    ]
