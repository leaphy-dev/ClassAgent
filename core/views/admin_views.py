"""管理员端：课程配置、用户与角色、任课/选课绑定、日志审计、系统状态。"""

import django
from django.contrib import messages
from django.db import connection
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from audit.models import AuditLog
from classroom.models import ClassRoom, Enrollment, Teaching
from core.forms import BindingForm, CourseForm, DifyConfigForm, UserCreateForm
from core.permissions import role_required
from core.presenters import (
    audit, base_context, form_context, render_context, stat_cards, table_context,
)
from course.models import WORKFLOW_SLOTS, Course, CourseDifyConfig, KnowledgePoint
from learning.algorithms import fuzzy_search
from learning.models import Assignment, Question, Submission
from user.models import User
from user.models.enum import UserRole


def _card_data():
    return stat_cards([
        ("课程总数", Course.objects.count(), "含草稿与归档"),
        ("开课中", Course.objects.filter(status=Course.Status.ACTIVE).count(), "顶层组织单位"),
        ("教学班", ClassRoom.objects.count(), "挂在各课程下"),
        ("注册用户", User.objects.count(), "三角色合计"),
    ])


@role_required(UserRole.ADMIN)
def dashboard(request):
    recent = [
        f"{log.created_at:%m-%d %H:%M} · {log.actor_label} · {log.action}"
        for log in AuditLog.objects.all()[:8]
    ]
    ctx = base_context(
        request, "管理员工作台", "课程配置、成员管理与系统运行一览",
        cards=_card_data(),
        quick=[
            {"label": "新建课程", "url": reverse("course_form"), "hint": "建立顶层组织单位"},
            {"label": "添加成员", "url": reverse("user_form"), "hint": "分配学生 / 教师 / 管理员"},
            {"label": "任课与选课", "url": reverse("bindings"), "hint": "把成员挂到教学班"},
            {"label": "审计日志", "url": reverse("audit_list"), "hint": "查看全部操作留痕"},
        ],
        recent=recent,
        recent_title="最近操作",
        template_name="panel/dashboard.html",
    )
    return render_context(request, ctx)


@role_required(UserRole.ADMIN)
def course_list(request):
    rows = []
    for course in Course.objects.all().order_by("code"):
        config = getattr(course, "dify_config", None)
        rows.append({
            "cells": [
                course.code, course.name, course.get_status_display(),
                course.classrooms.count(),
                course.knowledge_points.count(),
                Question.objects.filter(course=course).count(),
                "已就绪" if config and config.is_ready else ("已启用" if config and config.is_enabled else "占位"),
            ],
            "link": reverse("course_detail", args=[course.pk]),
            "actions": [{"label": "配置智能体", "url": reverse("course_config", args=[course.pk])}],
        })
    ctx = table_context(
        request, "课程配置", ["代码", "名称", "状态", "教学班", "知识点", "题目", "Dify"],
        rows, subtitle="每门课独占一份知识库与工作流配置",
        cards=stat_cards([
            ("课程", Course.objects.count(), "顶层单位"),
            ("已配置知识库", CourseDifyConfig.objects.exclude(dataset_id="").count(), "dataset_id 非空"),
            ("知识点", KnowledgePoint.objects.count(), "构成 DAG"),
            ("题目", Question.objects.count(), "本地题库"),
        ]),
        actions=[{"label": "＋ 新建课程", "url": reverse("course_form")}],
        note="「已就绪」= 启用 + 知识库 ID + 答疑工作流 ID + 服务端已注入 API Key。",
    )
    return render_context(request, ctx)


@role_required(UserRole.ADMIN)
def course_form(request):
    if request.method == "POST":
        form = CourseForm(request.POST)
        if form.is_valid():
            course = form.save(commit=False)
            course.created_by = request.user
            course.save()
            CourseDifyConfig.objects.get_or_create(course=course)
            audit(request, "新建课程", AuditLog.Category.COURSE, course.code, course.name)
            messages.success(request, f"课程 {course.code} 已创建，请继续配置智能体。")
            return redirect("course_detail", pk=course.pk)
    else:
        form = CourseForm()
    ctx = form_context(request, "新建课程", form, subtitle="课程是知识库、知识点与教学班的顶层单位",
                       back_url=reverse("course_list"),
                       note="保存后会自动生成一份占位 Dify 配置，默认不启用。")
    return render_context(request, ctx)


@role_required(UserRole.ADMIN)
def course_detail(request, pk):
    course = get_object_or_404(Course, pk=pk)
    config = getattr(course, "dify_config", None)
    classes = course.classrooms.all().annotate(
        student_count=Count("enrollments", distinct=True),
        teacher_count=Count("teachings", distinct=True),
    )
    from learning.services import course_progress

    labels = {"qa": "智能答疑", "quiz": "智能出题", "grading": "批改归因", "analytics": "学情摘要"}
    slots = [
        {"slot": slot, "label": labels.get(slot, slot),
         "value": (config.workflow_id(slot) if config else "") or "未配置"}
        for slot in WORKFLOW_SLOTS
    ]

    ctx = base_context(
        request, f"{course.code} · {course.name}", course.description,
        course=course, config=config, slots=slots, classes=classes,
        progress=course_progress(course),
        back_url=reverse("course_list"),
        template_name="panel/course_detail.html",
    )
    return render(request, "panel/course_detail.html", ctx)


@role_required(UserRole.ADMIN)
def course_config(request, pk):
    course = get_object_or_404(Course, pk=pk)
    config, _ = CourseDifyConfig.objects.get_or_create(course=course)
    initial = {
        "base_url": config.base_url,
        "dataset_id": config.dataset_id,
        "api_key_env": config.api_key_env,
        "prompt_version": config.prompt_version,
        "is_enabled": config.is_enabled,
    }
    for slot in WORKFLOW_SLOTS:
        initial[f"wf_{slot}"] = config.workflow_id(slot)
    if request.method == "POST":
        form = DifyConfigForm(request.POST, initial=initial)
        if form.is_valid():
            data = form.cleaned_data
            config.base_url = data["base_url"]
            config.dataset_id = data["dataset_id"].strip()
            config.api_key_env = data["api_key_env"].strip() or "DIFY_API_KEY"
            config.prompt_version = data["prompt_version"].strip() or "v1"
            config.workflows = form.workflows_dict()
            config.is_enabled = data["is_enabled"]
            config.save()
            audit(request, "修改课程智能体配置", AuditLog.Category.COURSE,
                  course.code, f"dataset={config.dataset_id}, enabled={config.is_enabled}")
            messages.success(request, f"{course.code} 的 Dify 配置已保存。")
            return redirect("course_detail", pk=course.pk)
    else:
        form = DifyConfigForm(initial=initial)
    ctx = form_context(
        request, f"{course.code} · 智能体配置", form,
        subtitle="密钥只存环境变量名，明文由部署环境注入，不写入数据库",
        back_url=reverse("course_detail", args=[pk]),
        note=f"当前就绪状态：{'已就绪' if config.is_ready else '未就绪'}（需要启用、知识库 ID、答疑工作流 ID 与服务端 API Key）。",
    )
    return render_context(request, ctx)


@role_required(UserRole.ADMIN)
def user_list(request):
    query = request.GET.get("q", "").strip()
    role = request.GET.get("role", "").strip()
    users = list(User.objects.all().order_by("role", "user_id"))
    if role:
        users = [u for u in users if u.role == role]
    if query:
        users = fuzzy_search(users, query, lambda u: f"{u.user_id} {u.display_name()} {u.email}")
    rows = []
    for user in users:
        rows.append({
            "cells": [
                user.user_id, user.display_name(), user.email,
                user.get_role_display(), "正常" if user.is_active else "已封禁",
                "是" if user.is_staff else "否",
            ],
            "actions": [{
                "label": "封禁" if user.is_active else "解封",
                "url": reverse("user_toggle", args=[user.pk]),
                "confirm": "确定要改变该账号的启用状态吗？" if user.pk != request.user.pk else "不能对自己的账号执行此操作",
                "disabled": user.pk == request.user.pk,
            }],
        })
    ctx = table_context(
        request, "用户与角色", ["账号", "姓名", "邮箱", "角色", "状态", "后台权限"],
        rows, subtitle="搜索走 Trie 前缀 + 编辑距离，支持账号 / 姓名 / 邮箱的模糊匹配",
        cards=stat_cards([
            ("管理员", User.objects.filter(role=UserRole.ADMIN).count(), "课程配置"),
            ("教师", User.objects.filter(role=UserRole.TEACHER).count(), "教学与批改"),
            ("学生", User.objects.filter(role=UserRole.STUDENT).count(), "学习与作答"),
            ("封禁", User.objects.filter(is_active=False).count(), "不可登录"),
        ]),
        actions=[{"label": "＋ 新增成员", "url": reverse("user_form")}],
        note=f"当前筛选：q={query or '全部'}，role={role or '全部'}",
    )
    return render_context(request, ctx)


@role_required(UserRole.ADMIN)
def user_form(request):
    if request.method == "POST":
        form = UserCreateForm(request.POST)
        if form.is_valid():
            data = form.cleaned_data
            user = User.objects.create_user(
                user_id=data["user_id"], email=data["email"], password=data["password"],
                role=data["role"], first_name=data["first_name"],
            )
            audit(request, "新增用户", AuditLog.Category.USER, user.user_id,
                  f"role={user.role}")
            messages.success(request, f"账号 {user.user_id} 已创建。")
            return redirect("user_list")
    else:
        form = UserCreateForm()
    ctx = form_context(request, "新增成员", form,
                       subtitle="创建后可在「任课与选课」里挂到教学班",
                       back_url=reverse("user_list"))
    return render_context(request, ctx)


@role_required(UserRole.ADMIN)
@require_POST
def user_toggle(request, pk):
    user = get_object_or_404(User, pk=pk)
    if user.pk == request.user.pk:
        messages.error(request, "不能封禁自己的账号。")
    elif user.is_active:
        user.ban()
        audit(request, "封禁用户", AuditLog.Category.USER, user.user_id)
        messages.success(request, f"{user.user_id} 已封禁，登录将被拒绝。")
    else:
        user.unban()
        audit(request, "解封用户", AuditLog.Category.USER, user.user_id)
        messages.success(request, f"{user.user_id} 已解封。")
    return redirect("user_list")


@role_required(UserRole.ADMIN)
def bindings(request):
    if request.method == "POST":
        action = request.POST.get("action", "")
        form = BindingForm(request.POST)
        if action.startswith("remove_"):
            item_id = request.POST.get("item_id")
            if action == "remove_teaching":
                Teaching.objects.filter(pk=item_id).delete()
                label = "解除任课绑定"
            else:
                Enrollment.objects.filter(pk=item_id).delete()
                label = "移除选课记录"
            audit(request, label, AuditLog.Category.CLASS, f"#{item_id}")
            messages.success(request, f"{label}完成。")
        elif form.is_valid():
            classroom = form.cleaned_data["classroom"]
            if action == "add_teaching" and form.cleaned_data["teacher"]:
                _, created = Teaching.objects.get_or_create(
                    classroom=classroom, teacher=form.cleaned_data["teacher"]
                )
                messages.success(request, "任课绑定已添加。" if created else "该任课关系已存在。")
                audit(request, "绑定任课教师", AuditLog.Category.CLASS, classroom.serial,
                      form.cleaned_data["teacher"].user_id)
            elif action == "add_student" and form.cleaned_data["student"]:
                _, created = Enrollment.objects.get_or_create(
                    classroom=classroom, student=form.cleaned_data["student"]
                )
                messages.success(request, "选课记录已添加。" if created else "该学生已在班级中。")
                audit(request, "添加选课学生", AuditLog.Category.CLASS, classroom.serial,
                      form.cleaned_data["student"].user_id)
            else:
                messages.error(request, "请选择要绑定的成员。")
        else:
            messages.error(request, "请选择教学班。")
        return redirect("bindings")

    classes = ClassRoom.objects.all().order_by("serial")
    selected = request.GET.get("classroom")
    current = classes.filter(pk=selected).first() if selected else classes.first()
    teachings = Teaching.objects.filter(classroom=current).select_related("teacher") if current else []
    enrollments = Enrollment.objects.filter(classroom=current).select_related("student") if current else []
    ctx = base_context(
        request, "任课与选课绑定", "把教师、学生挂到课程下的教学班",
        classes=classes, current=current,
        form=BindingForm(initial={"classroom": current.pk} if current else None),
        teachings=teachings, enrollments=enrollments,
        template_name="panel/bindings.html",
    )
    return render(request, "panel/bindings.html", ctx)


@role_required(UserRole.ADMIN)
def audit_list(request):
    category = request.GET.get("category", "")
    query = request.GET.get("q", "").strip()
    logs = AuditLog.objects.all()
    if category:
        logs = logs.filter(category=category)
    if query:
        logs = logs.filter(action__icontains=query) | logs.filter(target__icontains=query)
    logs = logs[:150]
    rows = [{
        "cells": [
            log.created_at.strftime("%m-%d %H:%M:%S"), log.actor_label or "匿名",
            log.get_category_display(), log.action, log.target,
            "成功" if log.success else "失败", log.ip,
        ]
    } for log in logs]
    ctx = table_context(
        request, "日志审计", ["时间", "操作人", "分类", "动作", "对象", "结果", "IP"],
        rows, subtitle="登录/登出由信号捕获；写请求由中间件兜底；关键业务动作单独记录",
        cards=stat_cards([
            ("日志总数", AuditLog.objects.count(), "全量留痕"),
            ("认证事件", AuditLog.objects.filter(category=AuditLog.Category.AUTH).count(), "登录/登出"),
            ("课程配置", AuditLog.objects.filter(category=AuditLog.Category.COURSE).count(), "配置变更"),
            ("教学活动", AuditLog.objects.filter(category=AuditLog.Category.LEARNING).count(), "作业/作答"),
        ]),
        categories=AuditLog.Category.choices,
        current_category=category, current_q=query,
        note="最多展示最近 150 条；可按分类与关键词筛选。",
    )
    return render_context(request, ctx)


@role_required(UserRole.ADMIN)
def system_status(request):
    counts = {
        "课程": Course.objects.count(),
        "知识点": KnowledgePoint.objects.count(),
        "教学班": ClassRoom.objects.count(),
        "任课绑定": Teaching.objects.count(),
        "选课记录": Enrollment.objects.count(),
        "题目": Question.objects.count(),
        "作业": Assignment.objects.count(),
        "提交": Submission.objects.count(),
        "审计日志": AuditLog.objects.count(),
    }
    from django.conf import settings as dj_settings

    ctx = base_context(
        request, "系统状态", "运行环境、数据规模与智能体就绪度",
        django_version=django.get_version(),
        db_engine=connection.settings_dict.get("ENGINE", ""),
        debug=dj_settings.DEBUG,
        time_zone=dj_settings.TIME_ZONE,
        counts=counts,
        dify_ready=sum(1 for c in CourseDifyConfig.objects.all() if c.is_ready),
        dify_total=CourseDifyConfig.objects.count(),
        template_name="panel/status.html",
    )
    return render(request, "panel/status.html", ctx)
