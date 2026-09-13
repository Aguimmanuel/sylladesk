from django.contrib import admin

from .models import Material


@admin.register(Material)
class MaterialAdmin(admin.ModelAdmin):
    list_display = ("title", "course", "week_no", "download_count", "is_deleted", "created_at")
    list_filter = ("course", "is_deleted")
    search_fields = ("title", "course__code")
