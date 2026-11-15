from django.conf import settings
from django.db import models

from classroom.models import ClassRoom

from .question import Question


class Assignment(models.Model):
    """一次作业，挂在教学班下；题目通过 AssignmentQuestion 有序关联。"""

    class Status(models.TextChoices):
        DRAFT = "DRAFT", "草稿"
        PUBLISHED = "PUBLISHED", "已发布"
        CLOSED = "CLOSED", "已截止"

    classroom = models.ForeignKey(
        ClassRoom,
        on_delete=models.CASCADE,
        related_name="assignments",
        verbose_name="教学班",
    )
    title = models.CharField("标题", max_length=128)
    description = models.TextField("说明", blank=True)
    due_at = models.DateTimeField("截止时间", null=True, blank=True)
    status = models.CharField("状态", max_length=16, choices=Status.choices, default=Status.DRAFT)
    questions = models.ManyToManyField(
        Question,
        through="AssignmentQuestion",
        related_name="assignments",
        verbose_name="题目",
        blank=True,
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_assignments",
        verbose_name="布置教师",
    )
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    published_at = models.DateTimeField("发布时间", null=True, blank=True)

    class Meta:
        verbose_name = "作业"
        verbose_name_plural = "作业"
        ordering = ["-created_at", "-id"]

    def __str__(self) -> str:
        return f"{self.classroom.serial} · {self.title}"

    @property
    def total_score(self) -> int:
        return sum(item.question.score for item in self.items.select_related("question"))

    def ordered_questions(self):
        return [item.question for item in self.items.select_related("question", "question__knowledge_point")]

    def publish(self):
        from django.utils import timezone

        if self.status != self.Status.PUBLISHED:
            self.status = self.Status.PUBLISHED
            self.published_at = timezone.now()
            self.save(update_fields=["status", "published_at"])


class AssignmentQuestion(models.Model):
    """作业与题目的有序关联（through 模型）。"""

    assignment = models.ForeignKey(
        Assignment, on_delete=models.CASCADE, related_name="items", verbose_name="作业"
    )
    question = models.ForeignKey(
        Question, on_delete=models.PROTECT, related_name="assignment_items", verbose_name="题目"
    )
    order = models.PositiveIntegerField("题序", default=0)

    class Meta:
        verbose_name = "作业题目"
        verbose_name_plural = "作业题目"
        ordering = ["order", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["assignment", "question"], name="uniq_assignment_question"
            )
        ]

    def __str__(self) -> str:
        return f"{self.assignment.title} #{self.order}"
