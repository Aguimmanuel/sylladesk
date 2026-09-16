from django.contrib import admin

from .models import Answer, Attempt, Question, Test


class QuestionInline(admin.TabularInline):
    model = Question
    extra = 0


@admin.register(Test)
class TestAdmin(admin.ModelAdmin):
    list_display = ("title", "course", "join_code", "status", "started_at", "closed_at",
                    "results_released_at")
    search_fields = ("title", "course__code", "join_code")
    inlines = [QuestionInline]


@admin.register(Attempt)
class AttemptAdmin(admin.ModelAdmin):
    list_display = ("test", "student", "current_section", "started_at", "final_deadline",
                    "submitted_at")
    list_filter = ("test",)
