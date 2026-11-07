from django.contrib.auth import logout
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import render, redirect
from django.views import View


class LogoutView(LoginRequiredMixin, View):
    """
    登出视图类
    """

    login_url = '/login/'

    def get(self, request):
        return render(request, "logout.html")

    def post(self, request):
        logout(request)
        return redirect(self.login_url)