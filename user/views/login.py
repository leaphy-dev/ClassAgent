from django.contrib.auth import login as auth_login
from django.shortcuts import render, redirect
from django.utils.http import url_has_allowed_host_and_scheme
from django.views import View

from ..forms import LoginForm

class LoginView(View):
    """
    登录视图类
    """
    _form_class = LoginForm

    def _safe_next(self, request):
        """只接受本站相对路径，避免 ?next= 被用作开放重定向。"""
        target = request.POST.get("next") or request.GET.get("next") or ""
        if target and url_has_allowed_host_and_scheme(
            target, allowed_hosts={request.get_host()}, require_https=request.is_secure()
        ):
            return target
        return "/"

    def get(self, request):
        return render(request, "login.html", {
            "form": self._form_class(request),
            "next": self._safe_next(request),
        })

    def post(self, request):
        form = self._form_class(request, data=request.POST)

        if form.is_valid():
            auth_login(request, form.get_user())
            return redirect(self._safe_next(request))

        return render(request, "login.html", {
            "form": form,
            "next": self._safe_next(request),
        })
