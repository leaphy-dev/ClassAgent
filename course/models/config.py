import os

from django.db import models

from .course import Course

# 平台侧预留的四个工作流槽位。每门课程只需把自己的应用 ID 填进 workflows。
WORKFLOW_SLOTS = ("qa", "quiz", "grading", "analytics")


class CourseDifyConfig(models.Model):
    """一门课程独占的 Dify 接入配置。

    安全约定：数据库里只保存环境变量的「名字」，不保存 API Key 本身。
    真正的密钥由部署环境注入，避免随仓库或数据库备份泄露。
    """

    course = models.OneToOneField(
        Course,
        on_delete=models.CASCADE,
        related_name="dify_config",
        verbose_name="课程",
    )
    base_url = models.CharField(
        "Dify API 地址",
        max_length=255,
        default="http://localhost/v1",
        help_text="自托管时形如 http://localhost/v1；具体路径以所部署版本官方文档为准",
    )
    dataset_id = models.CharField("知识库 ID", max_length=128, blank=True)
    workflows = models.JSONField(
        "工作流应用 ID",
        default=dict,
        blank=True,
        help_text='形如 {"qa": "...", "quiz": "...", "grading": "...", "analytics": "..."}',
    )
    api_key_env = models.CharField(
        "API Key 环境变量名",
        max_length=64,
        default="DIFY_API_KEY",
    )
    prompt_version = models.CharField("提示词版本", max_length=32, default="v1")
    is_enabled = models.BooleanField("是否启用", default=False)
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    class Meta:
        verbose_name = "课程 Dify 配置"
        verbose_name_plural = "课程 Dify 配置"

    def __str__(self) -> str:
        return f"{self.course.code} · Dify 配置"

    def workflow_id(self, slot: str) -> str:
        """取某槽位的应用 ID，未配置时返回空串。"""
        return (self.workflows or {}).get(slot, "")

    def resolve_api_key(self) -> str:
        """从部署环境解析 API Key，配置表里永远看不到明文。"""
        return os.environ.get(self.api_key_env, "")

    @property
    def is_ready(self) -> bool:
        """是否具备调用答疑工作流的最低条件。"""
        return bool(
            self.is_enabled
            and self.dataset_id
            and self.workflow_id("qa")
            and self.resolve_api_key()
        )
