from django.contrib import admin

from .models import Course, CourseDifyConfig, KnowledgePoint


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "status", "created_by", "created_at")
    list_filter = ("status",)
    search_fields = ("code", "name")


@admin.register(CourseDifyConfig)
class CourseDifyConfigAdmin(admin.ModelAdmin):
    list_display = ("course", "dataset_id", "prompt_version", "is_enabled", "is_ready")
    list_filter = ("is_enabled",)
    readonly_fields = ("is_ready",)


@admin.register(KnowledgePoint)
class KnowledgePointAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "course", "difficulty", "order")
    list_filter = ("course", "difficulty")
    search_fields = ("code", "name")
    filter_horizontal = ("prerequisites",)
