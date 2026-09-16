from django.contrib import admin

from .models import Assignment, Submission


@admin.register(Assignment)
class AssignmentAdmin(admin.ModelAdmin):
    list_display = ("title", "course", "due_at", "max_score", "is_active")
    list_filter = ("course",)
    search_fields = ("title", "course__code")


@admin.register(Submission)
class SubmissionAdmin(admin.ModelAdmin):
    list_display = ("assignment", "student", "attempt_no", "is_late", "submitted_at", "score")
    list_filter = ("assignment", "is_late")
    search_fields = ("student__full_name", "student__username")
