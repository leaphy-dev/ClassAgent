from django.conf import settings
from django.db import models


class AuditLog(models.Model):
    """审计日志：谁、在什么时候、对什么做了什么。

    通过 Django 信号记录登录/登出，通过中间件兜底记录所有已认证写请求，
    关键业务动作再由视图显式写入带中文说明的条目。
    """

    class Category(models.TextChoices):
        AUTH = "AUTH", "认证"
        COURSE = "COURSE", "课程配置"
        USER = "USER", "用户与角色"
        CLASS = "CLASS", "教学组织"
        LEARNING = "LEARNING", "教学活动"
        SYSTEM = "SYSTEM", "系统"

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_logs",
        verbose_name="操作人",
    )
    actor_label = models.CharField("操作人快照", max_length=64, blank=True,
                                   help_text="用户被删除后仍可追溯当时的账号")
    category = models.CharField("分类", max_length=16, choices=Category.choices,
                                default=Category.SYSTEM)
    action = models.CharField("动作", max_length=128)
    target = models.CharField("对象", max_length=128, blank=True)
    detail = models.TextField("详情", blank=True)
    method = models.CharField("请求方法", max_length=8, blank=True)
    path = models.CharField("请求路径", max_length=255, blank=True)
    ip = models.CharField("来源 IP", max_length=64, blank=True)
    success = models.BooleanField("成功", default=True)
    created_at = models.DateTimeField("发生时间", auto_now_add=True)

    class Meta:
        verbose_name = "审计日志"
        verbose_name_plural = "审计日志"
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["-created_at", "category"])]

    def __str__(self) -> str:
        return f"{self.actor_label or '匿名'} · {self.action}"


def record(actor=None, action: str = "", category: str = AuditLog.Category.SYSTEM,
           target: str = "", detail: str = "", request=None, success: bool = True) -> AuditLog:
    """统一写入口。视图里调用时传入 request 可自动带上路径与 IP。"""
    label = ""
    if actor is not None and getattr(actor, "is_authenticated", False):
        label = f"{actor.user_id} ({actor.display_name()})"
    return AuditLog.objects.create(
        actor=actor if getattr(actor, "is_authenticated", False) else None,
        actor_label=label,
        category=category,
        action=action,
        target=str(target)[:128],
        detail=detail,
        # 信号里的 request 可能是手工构造的 HttpRequest，method/path 会是 None，
        # 显式归一化，避免 NOT NULL 约束失败导致登录本身被审计逻辑拖垮。
        method=(getattr(request, "method", None) or "") if request else "",
        path=(getattr(request, "path", None) or "")[:255] if request else "",
        ip=_client_ip(request) if request else "",
        success=success,
    )


def _client_ip(request) -> str:
    """取客户端 IP；代理场景下读 X-Forwarded-For 的第一段。"""
    if request is None:
        return ""
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded:
        return forwarded.split(",")[0].strip()[:64]
    return request.META.get("REMOTE_ADDR", "")[:64]
