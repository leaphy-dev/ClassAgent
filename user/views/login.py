from django.contrib.auth import login as auth_login
from django.shortcuts import render, redirect
from django.views import View

from ..forms import LoginForm

class LoginView(View):
    """
    登录视图类
    """
    _form_class = LoginForm

    def get(self, request):
        return render(request, "login.html", {"form": self._form_class(request)})

    def post(self, request):
        form = self._form_class(request, data=request.POST)

        if form.is_valid():
            auth_login(request, form.get_user())
            return redirect("/")

        return render(request, "login.html", {"form": form})
