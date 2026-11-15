from django.conf import settings
from django.db import models

from .assignment import Assignment
from .question import Question


class Submission(models.Model):
    """一名学生对一次作业的一次提交。"""

    class Status(models.TextChoices):
        GRADED = "GRADED", "已判分"
        PENDING = "PENDING", "待复核"

    assignment = models.ForeignKey(
        Assignment, on_delete=models.CASCADE, related_name="submissions", verbose_name="作业"
    )
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="submissions",
        verbose_name="学生",
    )
    status = models.CharField("状态", max_length=16, choices=Status.choices, default=Status.PENDING)
    score = models.PositiveSmallIntegerField("得分", null=True, blank=True)
    submitted_at = models.DateTimeField("提交时间", auto_now_add=True)
    graded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="graded_submissions",
        verbose_name="复核教师",
    )
    graded_at = models.DateTimeField("复核时间", null=True, blank=True)

    class Meta:
        verbose_name = "作业提交"
        verbose_name_plural = "作业提交"
        ordering = ["-submitted_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["assignment", "student"], name="uniq_submission_assignment_student"
            )
        ]

    def __str__(self) -> str:
        return f"{self.student} → {self.assignment.title}"


class AnswerRecord(models.Model):
    """提交里的逐题作答，是学情分析、错题复盘的最小事实单元。"""

    submission = models.ForeignKey(
        Submission, on_delete=models.CASCADE, related_name="answers", verbose_name="提交"
    )
    question = models.ForeignKey(
        Question, on_delete=models.PROTECT, related_name="answer_records", verbose_name="题目"
    )
    answer = models.TextField("学生答案", blank=True)
    is_correct = models.BooleanField("是否正确", null=True, blank=True,
                                     help_text="NULL 表示简答题待教师复核")
    score = models.PositiveSmallIntegerField("本题得分", default=0)
    feedback = models.CharField("批注", max_length=255, blank=True)

    class Meta:
        verbose_name = "作答记录"
        verbose_name_plural = "作答记录"
        ordering = ["id"]
        constraints = [
            models.UniqueConstraint(
                fields=["submission", "question"], name="uniq_answer_submission_question"
            )
        ]

    def __str__(self) -> str:
        return f"{self.submission_id} / Q{self.question_id}"
