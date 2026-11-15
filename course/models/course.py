from django.conf import settings
from django.db import models


class Course(models.Model):
    """顶层组织单位：一门课程。

    课程下挂教学班、知识点图谱，并独占一份 Dify 知识库与工作流配置，
    使同一套系统结构可以复用于多门专业课程。
    """

    class Status(models.TextChoices):
        DRAFT = "DRAFT", "草稿"
        ACTIVE = "ACTIVE", "开课中"
        ARCHIVED = "ARCHIVED", "已归档"

    code = models.CharField("课程代码", max_length=32, unique=True)
    name = models.CharField("课程名称", max_length=128)
    description = models.TextField("课程简介", blank=True)
    status = models.CharField(
        "状态",
        max_length=16,
        choices=Status.choices,
        default=Status.ACTIVE,
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_courses",
        verbose_name="创建者",
    )
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    class Meta:
        verbose_name = "课程"
        verbose_name_plural = "课程"
        ordering = ["code"]

    def __str__(self) -> str:
        return f"{self.code} {self.name}"
