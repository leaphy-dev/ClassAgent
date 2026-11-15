"""教师端：班级学情、知识点治理、题库、作业布置与批改复核。"""

from django.contrib import messages
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from audit.models import AuditLog
from classroom.models import ClassRoom
from core.forms import AssignmentForm, KnowledgePointForm, QuestionForm
from core.permissions import role_required
from core.presenters import (
    audit, base_context, form_context, render_context, stat_cards, table_context,
)
from course.graph import CycleError, topological_order
from course.models import Course, KnowledgePoint
from learning.algorithms import select_questions
from learning.models import (
    Assignment,
    AssignmentQuestion,
    Question,
    Submission,
)
from learning.services import (
    class_analytics, course_progress, notify_classroom,
    question_stats, review_short_answers,
)
from user.models.enum import UserRole


def my_classrooms(user):
    return ClassRoom.objects.filter(teachings__teacher=user).distinct()


def my_courses(user):
    return Course.objects.filter(classrooms__in=my_classrooms(user)).distinct()


@role_required(UserRole.TEACHER)
def dashboard(request):
    classes = my_classrooms(request.user)
    assignments = Assignment.objects.filter(classroom__in=classes)
    ctx = base_context(
        request, "教师工作台", "我的教学班、题库与作业进度",
        cards=stat_cards([
            ("我的教学班", classes.count(), "任课绑定"),
            ("课程知识点", KnowledgePoint.objects.filter(course__in=my_courses(request.user)).count(), "DAG"),
            ("作业", assignments.count(), "含草稿"),
            ("待复核提交", Submission.objects.filter(
                assignment__in=assignments, status=Submission.Status.PENDING
            ).count(), "简答题批改"),
        ]),
        quick=[
            {"label": "布置作业", "url": reverse("assignment_form"), "hint": "手动选题或智能组卷"},
            {"label": "知识点治理", "url": reverse("knowledge_list"), "hint": "维护前置关系 DAG"},
            {"label": "题库管理", "url": reverse("question_list"), "hint": "录入题目与解析"},
            {"label": "班级学情", "url": reverse("class_list"), "hint": "完成率与正确率"},
        ],
        recent=[f"{a.classroom.serial} · {a.title} · {a.get_status_display()}"
                for a in assignments.order_by("-created_at")[:8]],
        recent_title="最近作业",
        template_name="panel/dashboard.html",
    )
    return render_context(request, ctx)


@role_required(UserRole.TEACHER)
def class_list(request):
    rows = []
    for classroom in my_classrooms(request.user).order_by("serial"):
        rows.append({
            "cells": [
                classroom.serial,
                classroom.course.name if classroom.course else "未挂课程",
                classroom.subject, classroom.term,
                classroom.enrollments.count(),
                classroom.assignments.count(),
            ],
            "link": reverse("class_detail", args=[classroom.pk]),
        })
    return render_context(request, table_context(
        request, "我的教学班", ["班级编号", "所属课程", "科目", "学期", "学生数", "作业数"],
        rows, subtitle="只看自己被绑定任课的教学班",
        cards=stat_cards([
            ("教学班", my_classrooms(request.user).count(), "任课中"),
            ("知识点", KnowledgePoint.objects.filter(course__in=my_courses(request.user)).count(), "可复用图谱"),
            ("题目", Question.objects.filter(course__in=my_courses(request.user)).count(), "本地题库"),
            ("作业提交", Submission.objects.filter(
                assignment__classroom__in=my_classrooms(request.user)).count(), "累计"),
        ]),
    ))


@role_required(UserRole.TEACHER)
def class_detail(request, pk):
    classroom = get_object_or_404(my_classrooms(request.user), pk=pk)
    analytics = class_analytics(classroom)
    assignments = classroom.assignments.all().order_by("-created_at")
    ctx = base_context(
        request, f"{classroom.serial} · 班级学情",
        f"{classroom.course.name if classroom.course else '未挂课程'} / {classroom.term}",
        classroom=classroom, analytics=analytics, assignments=assignments,
        progress=course_progress(classroom.course) if classroom.course else {},
        back_url=reverse("class_list"),
        template_name="panel/class_detail.html",
    )
    return render(request, "panel/class_detail.html", ctx)


@role_required(UserRole.TEACHER)
def knowledge_list(request):
    courses = my_courses(request.user)
    course_id = request.GET.get("course") or (courses.first().pk if courses.exists() else None)
    course = courses.filter(pk=course_id).first() if course_id else None
    rows = []
    if course:
        try:
            order = topological_order(course)
            for index, point in enumerate(order, 1):
                rows.append({
                    "cells": [
                        index, point.code, point.name, point.get_difficulty_display(),
                        "、".join(p.code for p in point.prerequisites.all()) or "—",
                        point.successors.count(),
                    ]
                })
        except CycleError as exc:
            messages.error(request, str(exc))
    ctx = table_context(
        request, "知识点治理", ["拓扑序", "编码", "名称", "难度", "前置知识点", "后继数"],
        rows, subtitle="按 Kahn 拓扑序展示，保证前置知识点排在前面",
        courses=courses, current_course=course,
        actions=[{"label": "＋ 新增知识点", "url": reverse("knowledge_form")}],
        note="保存前置关系时会重新做环检测；存在环将拒绝写入并回滚。",
    )
    return render_context(request, ctx)


@role_required(UserRole.TEACHER)
def knowledge_form(request):
    courses = my_courses(request.user)
    if request.method == "POST":
        form = KnowledgePointForm(request.POST, courses=courses)
        if form.is_valid():
            data = form.cleaned_data
            try:
                with transaction.atomic():
                    point = KnowledgePoint.objects.create(
                        course=data["course"], code=data["code"], name=data["name"],
                        description=data["description"], difficulty=data["difficulty"],
                        order=data["order"],
                    )
                    point.prerequisites.set(data["prerequisites"])
                    try:
                        topological_order(data["course"])
                    except CycleError as exc:
                        transaction.set_rollback(True)
                        raise exc
            except CycleError as exc:
                form.add_error("prerequisites", str(exc))
            else:
                audit(request, "新增知识点", AuditLog.Category.COURSE, point.code,
                      f"course={data['course'].code}")
                messages.success(request, f"知识点 {point.code} 已加入图谱。")
                return redirect("knowledge_list")
    else:
        form = KnowledgePointForm(courses=courses)
    return render_context(request, form_context(
        request, "新增知识点", form, subtitle="前置关系构成 DAG，是学习路径推荐的基础",
        back_url=reverse("knowledge_list"),
        note="只能从自己任课的课程里选择；前置知识点限定在同一课程内。",
    ))


@role_required(UserRole.TEACHER)
def question_list(request):
    courses = my_courses(request.user)
    questions = Question.objects.filter(course__in=courses).select_related(
        "course", "knowledge_point"
    ).order_by("course_id", "difficulty", "id")
    rows = [{
        "cells": [
            q.pk, q.course.code, q.get_qtype_display(), q.title[:48],
            q.knowledge_point.code if q.knowledge_point else "—",
            q.get_difficulty_display(), q.score, q.answer,
        ]
    } for q in questions]
    return render_context(request, table_context(
        request, "题库管理", ["ID", "课程", "题型", "题干", "知识点", "难度", "分值", "答案"],
        rows, subtitle="客观题自动判分，简答题留给教师复核",
        cards=stat_cards([
            ("题目总数", questions.count(), "本端可见"),
            ("单选题", questions.filter(qtype=Question.QType.SINGLE).count(), "自动判分"),
            ("判断题", questions.filter(qtype=Question.QType.JUDGE).count(), "自动判分"),
            ("简答题", questions.filter(qtype=Question.QType.SHORT).count(), "需复核"),
        ]),
        actions=[{"label": "＋ 录入题目", "url": reverse("question_form")}],
    ))


@role_required(UserRole.TEACHER)
def question_form(request):
    courses = my_courses(request.user)
    if request.method == "POST":
        form = QuestionForm(request.POST, courses=courses)
        if form.is_valid():
            data = form.cleaned_data
            question = Question.objects.create(
                course=data["course"], knowledge_point=data["knowledge_point"],
                qtype=data["qtype"], title=data["title"],
                options=QuestionForm.parse_options(data["options_text"]),
                answer=data["answer"].strip(), analysis=data["analysis"],
                difficulty=data["difficulty"], score=data["score"],
                created_by=request.user,
            )
            audit(request, "录入题目", AuditLog.Category.LEARNING, f"Q{question.pk}",
                  f"{data['course'].code} / 难度 {data['difficulty']}")
            messages.success(request, f"题目 Q{question.pk} 已入库。")
            return redirect("question_list")
    else:
        form = QuestionForm(courses=courses)
    return render_context(request, form_context(
        request, "录入题目", form, subtitle="题目挂到课程与知识点，供组卷和学情归因使用",
        back_url=reverse("question_list"),
        note="P3 接入 Dify 后，智能出题工作流生成的题目也走同一张表入库。",
    ))


@role_required(UserRole.TEACHER)
def assignment_list(request):
    classes = my_classrooms(request.user)
    assignments = Assignment.objects.filter(classroom__in=classes).select_related(
        "classroom"
    ).order_by("-created_at")
    rows = []
    for assignment in assignments:
        rows.append({
            "cells": [
                assignment.title, assignment.classroom.serial,
                assignment.get_status_display(), assignment.questions.count(),
                assignment.total_score, assignment.submissions.count(),
                assignment.due_at.strftime("%m-%d %H:%M") if assignment.due_at else "不限",
            ],
            "link": reverse("assignment_detail", args=[assignment.pk]),
            "actions": [] if assignment.status != Assignment.Status.DRAFT else [{
                "label": "发布", "url": reverse("assignment_publish", args=[assignment.pk]),
                "confirm": "发布后会通知全班学生，确定吗？",
            }],
        })
    return render_context(request, table_context(
        request, "作业布置", ["标题", "教学班", "状态", "题数", "满分", "提交数", "截止"],
        rows, subtitle="智能组卷按知识点覆盖 + 难度分布贪心选题",
        actions=[{"label": "＋ 布置作业", "url": reverse("assignment_form")}],
        cards=stat_cards([
            ("作业总数", assignments.count(), "我的教学班"),
            ("已发布", assignments.filter(status=Assignment.Status.PUBLISHED).count(), "学生可见"),
            ("草稿", assignments.filter(status=Assignment.Status.DRAFT).count(), "待发布"),
            ("待复核", Submission.objects.filter(
                assignment__in=assignments, status=Submission.Status.PENDING).count(), "简答题"),
        ]),
    ))


@role_required(UserRole.TEACHER)
def assignment_form(request):
    classes = my_classrooms(request.user)
    if request.method == "POST":
        form = AssignmentForm(request.POST, classrooms=classes)
        if form.is_valid():
            data = form.cleaned_data
            classroom = data["classroom"]
            course = classroom.course
            if data["mode"] == AssignmentForm.MODE_AUTO:
                pool = list(Question.objects.filter(course=course))
                chosen = select_questions(pool, data.get("auto_count") or 5)
                detail = f"智能组卷（贪心，池 {len(pool)} 题）"
            else:
                chosen = list(data["questions"])
                detail = f"手动选题 {len(chosen)} 题"
            if not chosen:
                form.add_error(None, "没有可用题目：请先到题库录入，或改用智能组卷。")
            else:
                with transaction.atomic():
                    assignment = Assignment.objects.create(
                        classroom=classroom, title=data["title"],
                        description=data["description"], due_at=data["due_at"],
                        created_by=request.user,
                    )
                    AssignmentQuestion.objects.bulk_create([
                        AssignmentQuestion(
                            assignment=assignment, question=q, order=index
                        ) for index, q in enumerate(chosen, 1)
                    ])
                audit(request, "布置作业", AuditLog.Category.LEARNING, assignment.title, detail)
                messages.success(request, f"《{assignment.title}》已创建，共 {len(chosen)} 题。")
                return redirect("assignment_detail", pk=assignment.pk)
    else:
        form = AssignmentForm(classrooms=classes)
    return render_context(request, form_context(
        request, "布置作业", form, subtitle="发布后学生会收到站内通知；发布前可随时调整",
        back_url=reverse("assignment_list"),
        note="智能组卷：先按知识点覆盖去重，再按难度分布补齐，复杂度 O(n log n)。",
    ))


@role_required(UserRole.TEACHER)
def assignment_detail(request, pk):
    assignment = get_object_or_404(
        Assignment.objects.filter(classroom__in=my_classrooms(request.user)), pk=pk
    )
    submissions = assignment.submissions.select_related("student").order_by("-submitted_at")
    ctx = base_context(
        request, f"作业详情 · {assignment.title}",
        f"{assignment.classroom.serial} / {assignment.get_status_display()}",
        assignment=assignment, stats=question_stats(assignment),
        submissions=submissions, now=timezone.now(),
        back_url=reverse("assignment_list"),
        template_name="panel/assignment_detail.html",
    )
    return render(request, "panel/assignment_detail.html", ctx)


@role_required(UserRole.TEACHER)
@require_POST
def assignment_publish(request, pk):
    assignment = get_object_or_404(
        Assignment.objects.filter(classroom__in=my_classrooms(request.user)), pk=pk
    )
    assignment.publish()
    notified = notify_classroom(assignment)
    audit(request, "发布作业", AuditLog.Category.LEARNING, assignment.title,
          f"通知 {notified} 名学生")
    messages.success(request, f"已发布，通知 {notified} 名学生。")
    return redirect("assignment_detail", pk=pk)


@role_required(UserRole.TEACHER)
def grading_detail(request, pk):
    submission = get_object_or_404(
        Submission.objects.filter(
            assignment__classroom__in=my_classrooms(request.user)
        ).select_related("student", "assignment"), pk=pk
    )
    if request.method == "POST":
        review_short_answers(submission, request.user, request.POST)
        audit(request, "复核作业", AuditLog.Category.LEARNING,
              f"{submission.student.user_id} / {submission.assignment.title}",
              f"得分 {submission.score}")
        messages.success(request, "复核完成，已通知学生。")
        return redirect("assignment_detail", pk=submission.assignment_id)
    answers = submission.answers.select_related("question", "question__knowledge_point")
    ctx = base_context(
        request, "批改复核", f"{submission.student.display_name()} · {submission.assignment.title}",
        submission=submission, answers=answers,
        back_url=reverse("assignment_detail", args=[submission.assignment_id]),
        template_name="panel/grading.html",
    )
    return render(request, "panel/grading.html", ctx)
