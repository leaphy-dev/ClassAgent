from django.shortcuts import redirect, render
from django.views import View

from core.permissions import role_home


class HomeView(View):
    """未登录显示入口页；已登录按角色分流到对应工作台。"""

    def get(self, request):
        if request.user.is_authenticated:
            return redirect(role_home(request.user))
        return render(request, "index.html")
