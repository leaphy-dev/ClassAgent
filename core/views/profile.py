from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect
from django.views import View


class UpdateDisplayNameView(LoginRequiredMixin, View):
    """修改当前登录用户自己的显示名称。

    只接受 POST：GET 访问这个地址会返回 405，因为它是纯表单提交入口，
    不应该被直接收藏或刷新。

    名字存进 first_name（display_name() 优先读 first_name，读不到才退回 user_id）。
    处理完统一跳回仪表盘，结果用 messages 显示成一条提示。
    """

    def post(self, request):
        name = (request.POST.get("display_name") or "").strip()

        if not name:
            messages.error(request, "名称不能为空。")
        elif len(name) > 150:
            # first_name 字段是 max_length=150，超了会报数据库错误，这里先挡住
            messages.error(request, "名称最多 150 个字符。")
        elif name == request.user.display_name():
            messages.info(request, "名称没有变化。")
        else:
            request.user.first_name = name
            request.user.save(update_fields=["first_name"])
            messages.success(request, f"名称已更新为「{name}」。")

        return redirect("core:dashboard")
