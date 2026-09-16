from django.contrib import admin

from .models import Answer, Attempt, Question, Test


class QuestionInline(admin.TabularInline):
    model = Question
    extra = 0


@admin.register(Test)
class TestAdmin(admin.ModelAdmin):
    list_display = ("title", "course", "join_code", "open_at", "close_at", "results_released_at")
    search_fields = ("title", "course__code", "join_code")
    inlines = [QuestionInline]


@admin.register(Attempt)
class AttemptAdmin(admin.ModelAdmin):
    list_display = ("test", "student", "started_at", "expires_at", "submitted_at")
    list_filter = ("test",)
