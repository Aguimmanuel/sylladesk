from django.contrib import admin

from .models import Announcement


@admin.register(Announcement)
class AnnouncementAdmin(admin.ModelAdmin):
    list_display = ("title", "course", "is_pinned", "is_active", "created_by", "created_at")
    list_filter = ("course", "is_pinned")
