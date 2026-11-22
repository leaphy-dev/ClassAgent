from django.conf import settings
from django.db import models

from ..managers import ClassroomManager


class Classroom(models.Model):
    """Teaching class. Subject and term are columns on this table."""
    objects = ClassroomManager()

    serial = models.UUIDField(
        primary_key=True, # 这是教学班主键
        verbose_name="serial",
        db_column="serial",
        max_length=32,
        unique=True,
        editable=False, # 这个字段不得随意改动
        help_text="Class serial, like a student ID.",
    )

    name = models.CharField(
        "name",
        db_column="name",
        max_length=32,
        unique=False,
        help_text="class name",
    )

    subject = models.CharField("subject",
                               max_length=64,
                               unique=False,)

    term = models.CharField("term",
                            max_length=32,
                            unique=False,)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        db_column="created_by",
        on_delete=models.PROTECT,
        related_name="created_classrooms",
        verbose_name="created by",
    )
    created_at = models.DateTimeField("created at",
                                      db_column="created_at",
                                      auto_now_add=True)
    updated_at = models.DateTimeField("updated at",
                                      db_column="updated_at",
                                      auto_now=True)

    class Meta:
        verbose_name = "class room"
        verbose_name_plural = "class rooms"

    def __str__(self) -> str:
        return f"{self.serial} ({self.subject}, {self.term})"

    @property
    def short_serial(self) -> str:
        """页面上展示用的短编号。

        serial 是 UUID 主键，完整长度 36 位，直接塞进表格会撑破列宽。
        这里只取前 8 位，完整值仍可通过 serial 取到。
        """
        return str(self.serial)[:8]