"""兜底审计：所有已登录用户的写请求都留痕。

视图若已经写过语义化日志，可设置 ``request._audit_logged = True`` 避免重复；
登录/登出由 signals.py 负责，因此这里排除 /login/ 与 /logout/。
"""

from .models import AuditLog, record

SKIP_PREFIXES = ("/static/", "/favicon.ico", "/login/", "/logout/")
WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


class AuditMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        try:
            if (
                request.method in WRITE_METHODS
                and getattr(request.user, "is_authenticated", False)
                and not request.path.startswith(SKIP_PREFIXES)
                and not getattr(request, "_audit_logged", False)
            ):
                response = self._write(request, response)
        except Exception:
            # 审计失败绝不能影响业务请求
            pass
        return response

    def _write(self, request, response):
        status = getattr(response, "status_code", 200)
        record(
            actor=request.user,
            action=f"{request.method} {request.path}",
            category=AuditLog.Category.SYSTEM,
            detail=f"HTTP {status}",
            request=request,
            success=200 <= status < 400,
        )
        return response
