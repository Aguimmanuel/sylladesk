from django.contrib import admin

from .models import AuditLog, File, FileBlob


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    """Append-only browser (FR-24/30). No add/change/delete — ever."""
    list_display = ("at", "action", "actor", "object_type", "object_id")
    list_filter = ("action",)
    search_fields = ("actor__username", "object_id", "detail")
    date_hierarchy = "at"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(File)
class FileAdmin(admin.ModelAdmin):
    list_display = ("original_name", "size_bytes", "mime", "uploaded_by", "created_at")
    search_fields = ("original_name", "sha256")


@admin.register(FileBlob)
class FileBlobAdmin(admin.ModelAdmin):
    """Bytes live here on the 'db' backend — read-only, never edited by hand."""
    list_display = ("key",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
