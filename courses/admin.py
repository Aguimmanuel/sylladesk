from django.contrib import admin

from .models import Course, Enrollment, RosterEntry


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ("code", "title", "session", "semester", "lecturer", "is_active")
    list_filter = ("semester", "is_active")
    search_fields = ("code", "title", "lecturer__full_name")


@admin.register(Enrollment)
class EnrollmentAdmin(admin.ModelAdmin):
    list_display = ("course", "user", "role_in_course", "is_active", "created_at")
    list_filter = ("role_in_course", "is_active")
    search_fields = ("course__code", "user__full_name", "user__username")


@admin.register(RosterEntry)
class RosterEntryAdmin(admin.ModelAdmin):
    list_display = ("reg_no", "course", "full_name", "claimed_by", "claimed_at", "is_active")
    list_filter = ("is_active",)
    search_fields = ("reg_no", "full_name", "course__code")
