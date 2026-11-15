from django.core.exceptions import ValidationError
from django.db import models

from .course import Course


class KnowledgePoint(models.Model):
    """课程知识点。

    通过 prerequisites 自关联形成有向无环图（DAG）：
    A 是 B 的前置，表示「先学 A 再学 B」；环会导致学习路径无解。
    """

    class Difficulty(models.IntegerChoices):
        INTRO = 1, "入门"
        BASIC = 2, "基础"
        NORMAL = 3, "进阶"
        HARD = 4, "较难"
        ADVANCED = 5, "拔高"

    course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE,
        related_name="knowledge_points",
        verbose_name="所属课程",
    )
    code = models.CharField("知识点编码", max_length=32)
    name = models.CharField("知识点名称", max_length=128)
    description = models.TextField("说明", blank=True)
    difficulty = models.PositiveSmallIntegerField(
        "难度",
        choices=Difficulty.choices,
        default=Difficulty.NORMAL,
    )
    order = models.PositiveIntegerField("教学顺序", default=0)
    prerequisites = models.ManyToManyField(
        "self",
        symmetrical=False,
        related_name="successors",
        blank=True,
        verbose_name="前置知识点",
    )
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    class Meta:
        verbose_name = "知识点"
        verbose_name_plural = "知识点"
        ordering = ["order", "code"]
        constraints = [
            models.UniqueConstraint(
                fields=["course", "code"],
                name="uniq_knowledge_point_course_code",
            )
        ]

    def __str__(self) -> str:
        return f"{self.code} {self.name}"

    def clean(self):
        super().clean()
        if self.pk and self.prerequisites.filter(pk=self.pk).exists():
            raise ValidationError("知识点不能把自己设为前置知识点。")
