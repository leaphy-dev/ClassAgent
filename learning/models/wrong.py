from django.conf import settings
from django.db import models

from .question import Question


class WrongQuestion(models.Model):
    """错题本。优先级不落库，由算法按错误次数 + 遗忘曲线实时计算。"""

    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="wrong_questions",
        verbose_name="学生",
    )
    question = models.ForeignKey(
        Question, on_delete=models.CASCADE, related_name="wrong_records", verbose_name="题目"
    )
    wrong_count = models.PositiveIntegerField("累计错误次数", default=1)
    last_wrong_at = models.DateTimeField("最近错误时间", auto_now=True)
    mastered = models.BooleanField("已掌握", default=False)
    mastered_at = models.DateTimeField("标记掌握时间", null=True, blank=True)

    class Meta:
        verbose_name = "错题"
        verbose_name_plural = "错题"
        ordering = ["-last_wrong_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["student", "question"], name="uniq_wrong_student_question"
            )
        ]

    def __str__(self) -> str:
        return f"{self.student} × Q{self.question_id}"
