from django.contrib import admin

from .models import (
    AnswerRecord,
    Assignment,
    AssignmentQuestion,
    Notification,
    Question,
    Submission,
    WrongQuestion,
)


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ("id", "course", "qtype", "difficulty", "score", "title")
    list_filter = ("course", "qtype", "difficulty")
    search_fields = ("title", "answer")


@admin.register(Assignment)
class AssignmentAdmin(admin.ModelAdmin):
    list_display = ("title", "classroom", "status", "created_by", "due_at")
    list_filter = ("status", "classroom")


@admin.register(AssignmentQuestion)
class AssignmentQuestionAdmin(admin.ModelAdmin):
    list_display = ("assignment", "question", "order")


@admin.register(Submission)
class SubmissionAdmin(admin.ModelAdmin):
    list_display = ("assignment", "student", "status", "score", "submitted_at")
    list_filter = ("status",)


@admin.register(AnswerRecord)
class AnswerRecordAdmin(admin.ModelAdmin):
    list_display = ("submission", "question", "is_correct", "score")


@admin.register(WrongQuestion)
class WrongQuestionAdmin(admin.ModelAdmin):
    list_display = ("student", "question", "wrong_count", "mastered", "last_wrong_at")
    list_filter = ("mastered",)


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("recipient", "kind", "title", "is_read", "created_at")
    list_filter = ("kind", "is_read")
