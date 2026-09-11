"""Cross-cutting models: the shared file registry + the append-only audit log.

Per PRD section 3.2 and PROJECT-STRUCTURE.md:
- File      — ONE registry for materials AND submissions (sha256 = dedup/integrity).
- FileBlob  — bytes for the "db" storage backend (free hosting F1: Postgres bytea).
- AuditLog  — append-only; written ONLY via core.auditing.audit() (FR-30).
"""
from django.conf import settings
from django.db import models


class FileBlob(models.Model):
    key = models.CharField(max_length=128, unique=True, db_index=True)
    data = models.BinaryField()

    def __str__(self):
        return self.key


class File(models.Model):
    storage_key = models.CharField(max_length=128, unique=True)
    original_name = models.CharField(max_length=255)
    mime = models.CharField(max_length=128, blank=True)
    size_bytes = models.PositiveBigIntegerField()
    sha256 = models.CharField(max_length=64, db_index=True)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="uploaded_files",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.original_name} ({self.size_bytes} B)"


class AuditLog(models.Model):
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="audit_entries",
    )
    action = models.CharField(max_length=64, db_index=True)
    object_type = models.CharField(max_length=64, blank=True)
    object_id = models.CharField(max_length=64, blank=True)
    detail = models.JSONField(default=dict, blank=True)
    at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-at"]
        verbose_name = "audit entry"

    def __str__(self):
        return f"{self.action} by {self.actor} at {self.at:%Y-%m-%d %H:%M}Z"
