from django.contrib import admin

from .models import ClassRoom, Enrollment, Teaching


@admin.register(ClassRoom)
class ClassRoomAdmin(admin.ModelAdmin):
    list_display = ("serial", "subject", "term", "created_by", "created_at")
    search_fields = ("serial", "subject", "term")


@admin.register(Teaching)
class TeachingAdmin(admin.ModelAdmin):
    list_display = ("classroom", "teacher", "created_at")
    search_fields = ("classroom__serial", "teacher__user_id")


@admin.register(Enrollment)
class EnrollmentAdmin(admin.ModelAdmin):
    list_display = ("classroom", "student", "created_at")
    search_fields = ("classroom__serial", "student__user_id")