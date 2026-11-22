from django.urls import path

from .views import DashboardView, HomeView, UpdateDisplayNameView

app_name = "core"

urlpatterns = [
    path("", HomeView.as_view(), name="home"),            # -> /
    path("dashboard/", DashboardView.as_view(), name="dashboard"),  # -> /dashboard/
    path("profile/name/", UpdateDisplayNameView.as_view(), name="update_name"),  # 改名表单提交
]
