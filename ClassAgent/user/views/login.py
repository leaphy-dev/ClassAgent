from django import forms
from django.contrib.auth.forms import AuthenticationForm, UsernameField
from django.contrib.auth import login as auth_login
from django.shortcuts import render, redirect
from django.views import View


class LoginForm(AuthenticationForm):
    """
    登录表单：字段由视图提供，模板只负责渲染与样式。
    """
    username = UsernameField(
        label="账号",
        error_messages={"required": "请输入账号。"},
    )
    password = forms.CharField(
        label="密码",
        strip=False,
        error_messages={"required": "请输入密码。"},
    )

    error_messages = {
        "invalid_login": "账号或密码不正确，请重试。",
        "inactive": "该账号已停用。",
    }


class LoginView(View):
    """
    登录视图类
    """
    form_class = LoginForm

    def get(self, request):
        return render(request, "login.html", {"form": self.form_class(request)})

    def post(self, request):
        form = self.form_class(request, data=request.POST)

        if form.is_valid():
            auth_login(request, form.get_user())
            return redirect("/")

        return render(request, "login.html", {"form": form})
