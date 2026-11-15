from django.conf import settings
from django.db import models


class Question(models.Model):
    """题库中的一道题。客观题可自动判分，简答题留给教师复核。"""

    class QType(models.TextChoices):
        SINGLE = "SINGLE", "单选题"
        JUDGE = "JUDGE", "判断题"
        SHORT = "SHORT", "简答题"

    class Difficulty(models.IntegerChoices):
        INTRO = 1, "入门"
        BASIC = 2, "基础"
        NORMAL = 3, "进阶"
        HARD = 4, "较难"
        ADVANCED = 5, "拔高"

    course = models.ForeignKey(
        "course.Course",
        on_delete=models.CASCADE,
        related_name="questions",
        verbose_name="所属课程",
    )
    knowledge_point = models.ForeignKey(
        "course.KnowledgePoint",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="questions",
        verbose_name="关联知识点",
    )
    qtype = models.CharField("题型", max_length=16, choices=QType.choices, default=QType.SINGLE)
    title = models.TextField("题干")
    options = models.JSONField("选项", default=list, blank=True,
                               help_text='单选题形如 [{"key":"A","text":"..."}, ...]')
    answer = models.CharField("参考答案", max_length=255, blank=True,
                              help_text="单选题填字母 A/B/C/D，判断题填 T/F，简答题填参考要点")
    analysis = models.TextField("解析", blank=True)
    difficulty = models.PositiveSmallIntegerField(
        "难度", choices=Difficulty.choices, default=Difficulty.NORMAL
    )
    score = models.PositiveSmallIntegerField("分值", default=5)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_questions",
        verbose_name="创建者",
    )
    created_at = models.DateTimeField("创建时间", auto_now_add=True)

    class Meta:
        verbose_name = "题目"
        verbose_name_plural = "题目"
        ordering = ["course_id", "difficulty", "id"]

    def __str__(self) -> str:
        return f"[{self.get_qtype_display()}] {self.title[:30]}"

    @property
    def is_objective(self) -> bool:
        return self.qtype in (self.QType.SINGLE, self.QType.JUDGE)

    def option_pairs(self):
        """把 JSON 选项规整成 (key, text) 列表，容错处理脏数据。"""
        if self.qtype == self.QType.JUDGE:
            return [("T", "正确"), ("F", "错误")]
        result = []
        for item in self.options or []:
            if isinstance(item, dict):
                result.append((str(item.get("key", "")), str(item.get("text", ""))))
            else:
                result.append((str(item), str(item)))
        return result

    def check_answer(self, given: str) -> bool | None:
        """客观题返回对错；简答题返回 None，表示需要教师复核。"""
        if not self.is_objective:
            return None
        return given.strip().upper() == self.answer.strip().upper()
