"""学生端：学习中心、作业作答、错题复盘、个人学情、知识图谱与通知。"""

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from audit.models import AuditLog
from core.forms import answer_form_for
from core.permissions import role_required
from core.presenters import (
    audit, base_context, render_context, stat_cards, table_context,
)
from course.graph import prerequisite_closure, topological_order
from course.models import Course, KnowledgePoint
from learning.algorithms import build_review_queue, review_due
from learning.models import Assignment, Notification, Submission, WrongQuestion
from learning.services import grade_submission, student_analytics
from user.models.enum import UserRole

ALL_ROLES = (UserRole.ADMIN, UserRole.TEACHER, UserRole.STUDENT)


def my_assignments(user):
    return Assignment.objects.filter(
        classroom__enrollments__student=user,
        status__in=[Assignment.Status.PUBLISHED, Assignment.Status.CLOSED],
    ).distinct()


def my_courses(user):
    return Course.objects.filter(
        classrooms__enrollments__student=user
    ).distinct()


@role_required(UserRole.STUDENT)
def dashboard(request):
    assignments = list(my_assignments(request.user).order_by("-published_at", "-created_at"))
    submissions = {s.assignment_id: s for s in Submission.objects.filter(student=request.user)}
    todo = [a for a in assignments if a.pk not in submissions]
    ctx = base_context(
        request, "学习中心", "我的课程、待办作业与学习进度",
        cards=stat_cards([
            ("在修课程", my_courses(request.user).count(), "按课程隔离"),
            ("待完成作业", len(todo), "已发布"),
            ("已提交", len(submissions), "含复核"),
            ("待复习错题", WrongQuestion.objects.filter(
                student=request.user, mastered=False).count(), "优先队列"),
        ]),
        quick=[
            {"label": "去作答", "url": reverse("student_assignments"), "hint": "查看待办作业"},
            {"label": "错题复盘", "url": reverse("wrong_list"), "hint": "按遗忘曲线排序"},
            {"label": "个人学情", "url": reverse("student_analytics"), "hint": "知识点掌握度"},
            {"label": "知识图谱", "url": reverse("graph_view"), "hint": "前置关系与学习路径"},
        ],
        recent=[f"{a.classroom.serial} · {a.title} · {'已交' if a.pk in submissions else '待完成'}"
                for a in assignments[:8]],
        recent_title="作业动态",
        template_name="panel/dashboard.html",
    )
    return render_context(request, ctx)


@role_required(UserRole.STUDENT)
def student_assignments(request):
    assignments = my_assignments(request.user).select_related("classroom").order_by(
        "-published_at", "-created_at"
    )
    submissions = {s.assignment_id: s for s in Submission.objects.filter(student=request.user)}
    rows = []
    for assignment in assignments:
        submission = submissions.get(assignment.pk)
        rows.append({
            "cells": [
                assignment.title,
                assignment.classroom.course.name if assignment.classroom.course else "—",
                assignment.questions.count(), assignment.total_score,
                "已提交" if submission else "待完成",
                f"{submission.score} 分" if submission else "—",
                assignment.due_at.strftime("%m-%d %H:%M") if assignment.due_at else "不限",
            ],
            "link": reverse("answer_view", args=[assignment.pk]),
        })
    return render_context(request, table_context(
        request, "我的作业", ["标题", "课程", "题数", "满分", "状态", "得分", "截止"],
        rows, subtitle="只显示自己所在教学班的已发布作业",
        cards=stat_cards([
            ("作业总数", assignments.count(), "已发布"),
            ("已提交", len(submissions), "不可重复提交"),
            ("待完成", assignments.count() - len(submissions), "尽快完成"),
            ("累计得分", sum(s.score or 0 for s in submissions.values()), "客观题 + 复核"),
        ]),
    ))


@role_required(UserRole.STUDENT)
def answer_view(request, pk):
    """未提交 → 作答表单；已提交 → 逐题结果页。同一 URL 承载两种状态。"""
    assignment = get_object_or_404(my_assignments(request.user), pk=pk)
    submission = Submission.objects.filter(
        assignment=assignment, student=request.user
    ).select_related("assignment").first()
    if submission:
        answers = submission.answers.select_related("question", "question__knowledge_point")
        ctx = base_context(
            request, f"作答结果 · {assignment.title}",
            f"得分 {submission.score} / {assignment.total_score} · {submission.get_status_display()}",
            submission=submission, answers=answers, assignment=assignment,
            back_url=reverse("student_assignments"),
            template_name="panel/result.html",
        )
        return render(request, "panel/result.html", ctx)

    if assignment.status == Assignment.Status.CLOSED:
        messages.error(request, "该作业已截止，不能再提交。")
        return redirect("student_assignments")

    if request.method == "POST":
        form = answer_form_for(assignment)(request.POST)
        if form.is_valid():
            submission = grade_submission(assignment, request.user, form.cleaned_data)
            audit(request, "提交作业", AuditLog.Category.LEARNING, assignment.title,
                  f"得分 {submission.score} / {assignment.total_score}")
            messages.success(request, "提交成功，客观题已自动判分。")
            return redirect("answer_view", pk=pk)
    else:
        form = answer_form_for(assignment)()
    ctx = base_context(
        request, f"作答 · {assignment.title}",
        f"{assignment.classroom.serial} · 共 {assignment.questions.count()} 题 / 满分 {assignment.total_score}",
        assignment=assignment, form=form,
        questions=assignment.ordered_questions(),
        back_url=reverse("student_assignments"),
        template_name="panel/answer.html",
    )
    return render(request, "panel/answer.html", ctx)


@role_required(UserRole.STUDENT)
def wrong_list(request):
    wrongs = WrongQuestion.objects.filter(
        student=request.user, mastered=False
    ).select_related("question", "question__knowledge_point", "question__course")
    now = timezone.now()
    queue = build_review_queue(wrongs, now, limit=50)
    rows = []
    for priority, wrong in queue:
        question = wrong.question
        elapsed = (now - wrong.last_wrong_at).total_seconds() / 3600 if wrong.last_wrong_at else 0
        rows.append({
            "cells": [
                f"{priority:.4f}", question.title[:48],
                question.knowledge_point.name if question.knowledge_point else "未分类",
                question.get_difficulty_display(), wrong.wrong_count,
                f"{elapsed:.1f} 小时后",
                f"{review_due(elapsed).total_seconds() / 3600:.1f} 小时后",
            ],
            "actions": [{
                "label": "标记已掌握", "url": reverse("wrong_master", args=[wrong.pk]),
            }],
        })
    return render_context(request, table_context(
        request, "错题复盘", ["优先级", "题目", "知识点", "难度", "错误次数", "距上次", "建议复习"],
        rows, subtitle="优先级 = 错误次数 × 遗忘残留 × 难度权重，最小堆取 Top-K",
        cards=stat_cards([
            ("待复习错题", wrongs.count(), "未掌握"),
            ("已掌握", WrongQuestion.objects.filter(student=request.user, mastered=True).count(), "已移出队列"),
            ("最高优先级", f"{queue[0][0]:.2f}" if queue else "—", "队首"),
            ("算法", "O(n log k)", "优先队列"),
        ]),
        note="复习间隔按简化艾宾浩斯曲线安排；标记已掌握后优先级归零，不再出现在队列中。",
    ))


@role_required(UserRole.STUDENT)
@require_POST
def wrong_master(request, pk):
    wrong = get_object_or_404(WrongQuestion, pk=pk, student=request.user)
    wrong.mastered = True
    wrong.mastered_at = timezone.now()
    wrong.save(update_fields=["mastered", "mastered_at"])
    audit(request, "标记错题已掌握", AuditLog.Category.LEARNING, f"Q{wrong.question_id}")
    messages.success(request, "已移出复习队列。")
    return redirect("wrong_list")


@role_required(UserRole.STUDENT)
def analytics_view(request):
    data = student_analytics(request.user)
    recommendations = []
    for weak in data["weak_points"][:3]:
        point = KnowledgePoint.objects.filter(
            course__in=my_courses(request.user), name=weak["label"]
        ).first()
        if point:
            try:
                pres = prerequisite_closure(point.course, point)[:3]
            except ValueError:
                pres = []
            recommendations.append({
                "point": weak["label"], "rate": weak["rate"],
                "pres": [p.name for p in pres] or ["已是基础知识点，建议直接重做错题"],
            })
    ctx = base_context(
        request, "个人学情", "完成率、正确率、知识点掌握度与复习建议",
        data=data, recommendations=recommendations,
        template_name="panel/analytics.html",
    )
    return render(request, "panel/analytics.html", ctx)


@role_required(UserRole.STUDENT)
def graph_view(request):
    courses = my_courses(request.user)
    course_id = request.GET.get("course") or (courses.first().pk if courses.exists() else None)
    course = courses.filter(pk=course_id).first() if course_id else None
    levels = []
    if course:
        try:
            order = topological_order(course)
        except ValueError:
            order = list(course.knowledge_points.all())
        level_of = {}
        for point in order:
            pres = [p.pk for p in point.prerequisites.all() if p.pk in level_of]
            level_of[point.pk] = max((level_of[p] + 1 for p in pres), default=0)
        grouped = {}
        for point in order:
            grouped.setdefault(level_of[point.pk], []).append(point)
        levels = [{"level": i, "points": grouped[i]} for i in sorted(grouped)]
    ctx = base_context(
        request, "知识图谱", "按拓扑层级展示前置关系与推荐学习路径",
        courses=courses, course=course, levels=levels,
        template_name="panel/graph.html",
    )
    return render(request, "panel/graph.html", ctx)


@role_required(*ALL_ROLES)
def notification_list(request):
    notes = request.user.notifications.all()[:100]
    rows = [{
        "cells": [
            note.created_at.strftime("%m-%d %H:%M"), note.get_kind_display(),
            note.title, note.body[:60], "已读" if note.is_read else "未读",
        ],
        "actions": [] if note.is_read else [{
            "label": "标记已读", "url": reverse("notification_read", args=[note.pk]),
        }],
    } for note in notes]
    return render_context(request, table_context(
        request, "通知中心", ["时间", "类型", "标题", "内容", "状态"], rows,
        subtitle="作业发布、批改完成与系统消息",
        cards=stat_cards([
            ("全部通知", request.user.notifications.count(), "近期"),
            ("未读", request.user.notifications.filter(is_read=False).count(), "待查看"),
            ("作业通知", request.user.notifications.filter(kind=Notification.Kind.ASSIGNMENT).count(), "新作业"),
            ("批改通知", request.user.notifications.filter(kind=Notification.Kind.FEEDBACK).count(), "成绩"),
        ]),
    ))


@role_required(*ALL_ROLES)
@require_POST
def notification_read(request, pk):
    note = get_object_or_404(Notification, pk=pk, recipient=request.user)
    note.is_read = True
    note.save(update_fields=["is_read"])
    return redirect("notification_list")
