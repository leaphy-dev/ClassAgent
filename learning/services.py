"""业务服务层：把「提交 → 判分 → 错题 → 通知 → 学情」串成闭环。

视图只做参数校验与渲染，所有跨模型写操作集中在这里，便于单测与事务控制。
"""

from __future__ import annotations

from django.db import transaction
from django.db.models import Avg, Count, Q
from django.utils import timezone

from classroom.models import Enrollment
from course.models import KnowledgePoint

from .algorithms import mastery_summary, multi_key_rank, review_priority
from .models import (
    AnswerRecord,
    Assignment,
    Notification,
    Question,
    Submission,
    WrongQuestion,
)


def grade_submission(assignment: Assignment, student, answers: dict[str, str]) -> Submission:
    """创建提交并逐题判分，自动维护错题本；含简答题时标记待教师复核。

    answers 形如 {"q_<pk>": "A"}。客观题立即给分，简答题 score=0、is_correct=None。
    """
    with transaction.atomic():
        submission = Submission.objects.create(
            assignment=assignment,
            student=student,
            status=Submission.Status.GRADED,
            score=0,
        )
        total = 0
        has_short = False
        for question in assignment.ordered_questions():
            given = (answers.get(f"q_{question.pk}") or "").strip()
            correct = question.check_answer(given)
            earned = question.score if correct is True else 0
            record = AnswerRecord.objects.create(
                submission=submission,
                question=question,
                answer=given,
                is_correct=correct,
                score=earned,
            )
            total += earned
            if correct is None:
                has_short = True
            if correct is False or correct is None:
                wrong, created = WrongQuestion.objects.get_or_create(
                    student=student,
                    question=question,
                    defaults={"wrong_count": 0, "mastered": False},
                )
                if not created:
                    wrong.wrong_count += 1
                    wrong.mastered = False
                    wrong.mastered_at = None
                    wrong.save(update_fields=["wrong_count", "mastered", "mastered_at"])
                else:
                    wrong.wrong_count = 1
                    wrong.save(update_fields=["wrong_count"])
        submission.score = total
        submission.status = (
            Submission.Status.PENDING if has_short else Submission.Status.GRADED
        )
        submission.save(update_fields=["score", "status"])
    return submission


def review_short_answers(submission: Submission, teacher, decisions: dict[str, str]) -> Submission:
    """教师复核简答题：decisions 形如 {"a_<pk>": "3", "c_<pk>": "on"}。"""
    with transaction.atomic():
        total = 0
        for record in submission.answers.select_related("question"):
            question = record.question
            if question.is_objective:
                total += record.score
                continue
            correct = decisions.get(f"c_{record.pk}") == "on"
            earned = min(int(decisions.get(f"a_{record.pk}") or 0), question.score)
            record.is_correct = correct
            record.score = earned
            record.feedback = decisions.get(f"f_{record.pk}", "")
            record.save(update_fields=["is_correct", "score", "feedback"])
            total += earned
            if not correct:
                wrong, _ = WrongQuestion.objects.get_or_create(
                    student=submission.student, question=question
                )
                wrong.mastered = False
                wrong.save(update_fields=["mastered"])
        submission.score = total
        submission.status = Submission.Status.GRADED
        submission.graded_by = teacher
        submission.graded_at = timezone.now()
        submission.save(update_fields=["score", "status", "graded_by", "graded_at"])
        Notification.objects.create(
            recipient=submission.student,
            kind=Notification.Kind.FEEDBACK,
            title=f"《{submission.assignment.title}》批改完成",
            body=f"本次得分 {total} / {submission.assignment.total_score}",
        )
    return submission


def notify_classroom(assignment: Assignment) -> int:
    """作业发布时给教学班全体学生发站内通知。"""
    student_ids = Enrollment.objects.filter(classroom=assignment.classroom).values_list(
        "student_id", flat=True
    )
    Notification.objects.bulk_create([
        Notification(
            recipient_id=student_id,
            kind=Notification.Kind.ASSIGNMENT,
            title=f"新作业：{assignment.title}",
            body=f"{assignment.classroom.serial} · 共 {assignment.questions.count()} 题，"
                 f"满分 {assignment.total_score} 分",
        )
        for student_id in student_ids
    ])
    return len(student_ids)


def class_analytics(classroom) -> list[dict]:
    """班级学情：完成率、平均分、正确率、错题数，多关键字排名。"""
    assignments = list(classroom.assignments.all())
    published = [a for a in assignments if a.status != Assignment.Status.DRAFT]
    total = len(published)
    rows = []
    for enrollment in Enrollment.objects.filter(classroom=classroom).select_related("student"):
        student = enrollment.student
        submissions = list(Submission.objects.filter(student=student, assignment__in=published))
        answers = list(AnswerRecord.objects.filter(submission__in=submissions))
        graded = [a for a in answers if a.is_correct is not None]
        avg = sum(s.score or 0 for s in submissions) / len(submissions) if submissions else 0
        rows.append({
            "student": student,
            "name": student.display_name(),
            "user_id": student.user_id,
            "done": len(submissions),
            "total": total,
            "completion": round(len(submissions) / total, 4) if total else 0.0,
            "avg_score": round(avg, 2),
            "accuracy": round(
                sum(1 for a in graded if a.is_correct) / len(graded), 4
            ) if graded else 0.0,
            "wrong": WrongQuestion.objects.filter(student=student, mastered=False).count(),
        })
    return multi_key_rank(rows, ["completion", "avg_score", "user_id"])


def student_analytics(student, course=None) -> dict:
    """个人学情：完成率、正确率、知识点掌握度、薄弱点与复习建议。"""
    submission_qs = Submission.objects.filter(student=student).select_related("assignment")
    if course:
        submission_qs = submission_qs.filter(
            assignment__classroom__course=course
        )
    submissions = list(submission_qs)
    answers = list(AnswerRecord.objects.filter(submission__in=submissions)
                   .select_related("question__knowledge_point"))
    graded = [a for a in answers if a.is_correct is not None]

    assignment_qs = Assignment.objects.filter(status__in=[
        Assignment.Status.PUBLISHED, Assignment.Status.CLOSED
    ])
    if course:
        assignment_qs = assignment_qs.filter(classroom__course=course)
    available = list(
        assignment_qs.filter(classroom__enrollments__student=student).distinct()
    )
    done_ids = {s.assignment_id for s in submissions}

    summary = mastery_summary(answers)
    weak = sorted(summary.values(), key=lambda row: (row["rate"], -row["total"]))[:5]
    wrongs = list(
        WrongQuestion.objects.filter(student=student, mastered=False)
        .select_related("question__knowledge_point", "question__course")
    )
    now = timezone.now()
    queue = sorted(
        ((review_priority(w, now), w) for w in wrongs),
        key=lambda pair: pair[0], reverse=True,
    )[:5]

    return {
        "submissions": submissions,
        "answers": answers,
        "available_count": len(available),
        "done_count": len(done_ids),
        "completion": round(len(done_ids) / len(available), 4) if available else 0.0,
        "avg_score": round(
            sum(s.score or 0 for s in submissions) / len(submissions), 2
        ) if submissions else 0.0,
        "accuracy": round(
            sum(1 for a in graded if a.is_correct) / len(graded), 4
        ) if graded else 0.0,
        "mastery": sorted(summary.values(), key=lambda row: row["label"]),
        "weak_points": weak,
        "review_queue": queue,
        "total_score": sum(s.score or 0 for s in submissions),
    }


def question_stats(assignment: Assignment) -> list[dict]:
    """逐题正确率，供教师端作业详情展示。"""
    result = []
    for item in assignment.items.select_related("question", "question__knowledge_point"):
        question = item.question
        agg = AnswerRecord.objects.filter(
            submission__assignment=assignment, question=question, is_correct__isnull=False
        ).aggregate(total=Count("id"), correct=Count("id", filter=Q(is_correct=True)), avg=Avg("score"))
        total = agg["total"] or 0
        result.append({
            "order": item.order,
            "question": question,
            "total": total,
            "correct": agg["correct"] or 0,
            "rate": round((agg["correct"] or 0) / total, 4) if total else 0.0,
            "avg_score": round(agg["avg"] or 0, 2),
        })
    return result


def course_progress(course) -> dict:
    """管理员 / 教师首页用的课程概览数字。"""
    return {
        "points": KnowledgePoint.objects.filter(course=course).count(),
        "questions": Question.objects.filter(course=course).count(),
        "assignments": Assignment.objects.filter(classroom__course=course).count(),
        "submissions": Submission.objects.filter(assignment__classroom__course=course).count(),
        "classes": course.classrooms.count(),
    }
