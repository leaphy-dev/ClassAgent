"""页面数据构造助手：让三端列表页共用一套表格模板，避免模板碎片化。"""

from django.urls import reverse

from core.permissions import role_home, role_label


def base_context(request, title, subtitle="", **extra):
    """所有三端页面共享的上下文。"""
    ctx = {
        "title": title,
        "subtitle": subtitle,
        "role_label": role_label(request.user),
        "role_home": role_home(request.user),
        "user": request.user,
        "nav": nav_items(request.user),
        "unread_count": request.user.notifications.filter(is_read=False).count()
        if request.user.is_authenticated else 0,
    }
    ctx.update(extra)
    return ctx


def nav_items(user) -> list[dict]:
    """按角色生成侧边栏导航。"""
    role = getattr(user, "role", "")
    if user.is_admin():
        items = [
            ("工作台", "manage_dashboard"),
            ("课程配置", "course_list"),
            ("用户与角色", "user_list"),
            ("任课与选课", "bindings"),
            ("审计日志", "audit_list"),
            ("系统状态", "system_status"),
        ]
    elif user.is_teacher():
        items = [
            ("工作台", "teacher_dashboard"),
            ("我的教学班", "class_list"),
            ("知识点治理", "knowledge_list"),
            ("题库管理", "question_list"),
            ("作业布置", "assignment_list"),
        ]
    else:
        items = [
            ("学习中心", "student_dashboard"),
            ("我的作业", "student_assignments"),
            ("错题复盘", "wrong_list"),
            ("个人学情", "student_analytics"),
            ("知识图谱", "graph_view"),
        ]
    result = []
    for label, name in items:
        result.append({"label": label, "url": reverse(name)})
    result.append({"label": "通知中心", "url": reverse("notification_list")})
    return result


def table_context(request, title, columns, rows, *, subtitle="", actions=None,
                  cards=None, note="", **extra):
    """通用列表页上下文。

    rows: [{"cells": [...], "link": url|None, "actions": [{"label","url","confirm"}]}]
    """
    ctx = base_context(request, title, subtitle, **extra)
    ctx.update({
        "columns": columns,
        "rows": rows,
        "top_actions": actions or [],
        "cards": cards or [],
        "note": note,
        "template_name": "panel/table.html",
    })
    return ctx


def form_context(request, title, form, *, subtitle="", submit="保存",
                 back_url="", back_label="返回", note="", **extra):
    ctx = base_context(request, title, subtitle, **extra)
    ctx.update({
        "form": form,
        "submit_label": submit,
        "back_url": back_url,
        "back_label": back_label,
        "note": note,
        "template_name": "panel/form.html",
    })
    return ctx


def stat_cards(items) -> list[dict]:
    """[(标签, 数值, 副标题)] → 统计卡数据。"""
    return [{"label": a, "value": b, "hint": c} for a, b, c in items]


def render_context(request, ctx):
    """按上下文里的 template_name 渲染，减少每个视图的样板代码。"""
    from django.shortcuts import render

    payload = dict(ctx)
    name = payload.pop("template_name", "panel/table.html")
    return render(request, name, payload)


def audit(request, action, category, target="", detail=""):
    """写一条语义化审计日志，并告诉中间件本次请求无需重复兜底记录。"""
    from audit.models import record

    entry = record(
        actor=request.user, action=action, category=category,
        target=target, detail=detail, request=request,
    )
    request._audit_logged = True
    return entry
