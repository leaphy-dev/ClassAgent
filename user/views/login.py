from django import forms
from django.contrib.auth.forms import AuthenticationForm, UsernameField
from django.contrib.auth import login as auth_login
from django.shortcuts import render, redirect
from django.views import View


class LoginView(View):
    """
    登录视图类
    """
    form_class = AuthenticationForm

    def get(self, request):
        return render(request, "login.html", {"form": self.form_class(request)})

    def post(self, request):
        form = self.form_class(request, data=request.POST)

        if form.is_valid():
            auth_login(request, form.get_user())
            return redirect("/")

        return render(request, "login.html", {"form": form})
