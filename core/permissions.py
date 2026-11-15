"""三端 RBAC：统一的角色判定与访问控制。

权限只认 user.role（配合 User 的 is_admin/is_teacher/is_student 方法），
不做「超级用户自动放行」，避免演示时管理员越权访问教师/学生端。
"""

from functools import wraps

from django.conf import settings
from django.contrib.auth.views import redirect_to_login
from django.shortcuts import render

from user.models.enum import UserRole

ROLE_HOME = {
    UserRole.ADMIN: "/manage/",
    UserRole.TEACHER: "/teacher/",
    UserRole.STUDENT: "/student/",
}

ROLE_LABEL = {
    UserRole.ADMIN: "管理员端",
    UserRole.TEACHER: "教师端",
    UserRole.STUDENT: "学生端",
    UserRole.GUEST: "访客",
}


def role_home(user) -> str:
    return ROLE_HOME.get(getattr(user, "role", ""), "/")


def role_label(user) -> str:
    return ROLE_LABEL.get(getattr(user, "role", ""), "访客")


def role_required(*roles):
    """视图装饰器：未登录跳登录页并带 ?next=，角色不符返回 403。"""
    def decorator(view):
        @wraps(view)
        def wrapper(request, *args, **kwargs):
            user = request.user
            if not user.is_authenticated:
                return redirect_to_login(
                    request.get_full_path(), settings.LOGIN_URL, "next"
                )
            allowed = (
                (UserRole.ADMIN in roles and user.is_admin())
                or (UserRole.TEACHER in roles and user.is_teacher())
                or (UserRole.STUDENT in roles and user.is_student())
            )
            if not allowed:
                return render(
                    request,
                    "panel/403.html",
                    {"required": " / ".join(ROLE_LABEL.get(r, r) for r in roles)},
                    status=403,
                )
            return view(request, *args, **kwargs)
        return wrapper
    return decorator
