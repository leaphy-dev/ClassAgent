"""三端业务路由。管理员 /manage/，教师 /teacher/，学生 /student/。"""

from django.urls import path

from .views import admin_views as a
from .views import student_views as s
from .views import teacher_views as t

urlpatterns = [
    # 管理员端
    path("manage/", a.dashboard, name="manage_dashboard"),
    path("manage/courses/", a.course_list, name="course_list"),
    path("manage/courses/new/", a.course_form, name="course_form"),
    path("manage/courses/<int:pk>/", a.course_detail, name="course_detail"),
    path("manage/courses/<int:pk>/config/", a.course_config, name="course_config"),
    path("manage/users/", a.user_list, name="user_list"),
    path("manage/users/new/", a.user_form, name="user_form"),
    path("manage/users/<int:pk>/toggle/", a.user_toggle, name="user_toggle"),
    path("manage/bindings/", a.bindings, name="bindings"),
    path("manage/audit/", a.audit_list, name="audit_list"),
    path("manage/status/", a.system_status, name="system_status"),

    # 教师端
    path("teacher/", t.dashboard, name="teacher_dashboard"),
    path("teacher/classes/", t.class_list, name="class_list"),
    path("teacher/classes/<int:pk>/", t.class_detail, name="class_detail"),
    path("teacher/knowledge/", t.knowledge_list, name="knowledge_list"),
    path("teacher/knowledge/new/", t.knowledge_form, name="knowledge_form"),
    path("teacher/questions/", t.question_list, name="question_list"),
    path("teacher/questions/new/", t.question_form, name="question_form"),
    path("teacher/assignments/", t.assignment_list, name="assignment_list"),
    path("teacher/assignments/new/", t.assignment_form, name="assignment_form"),
    path("teacher/assignments/<int:pk>/", t.assignment_detail, name="assignment_detail"),
    path("teacher/assignments/<int:pk>/publish/", t.assignment_publish, name="assignment_publish"),
    path("teacher/submissions/<int:pk>/", t.grading_detail, name="grading_detail"),

    # 学生端
    path("student/", s.dashboard, name="student_dashboard"),
    path("student/assignments/", s.student_assignments, name="student_assignments"),
    path("student/assignments/<int:pk>/", s.answer_view, name="answer_view"),
    path("student/wrong/", s.wrong_list, name="wrong_list"),
    path("student/wrong/<int:pk>/master/", s.wrong_master, name="wrong_master"),
    path("student/analytics/", s.analytics_view, name="student_analytics"),
    path("student/graph/", s.graph_view, name="graph_view"),

    # 三端共用
    path("notifications/", s.notification_list, name="notification_list"),
    path("notifications/<int:pk>/read/", s.notification_read, name="notification_read"),
]
