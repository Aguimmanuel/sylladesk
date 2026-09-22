from django.conf import settings
from django.db import models

from courses.models import Course


class Announcement(models.Model):
    """A course notice: in-app only, pinned first then newest."""

    course = models.ForeignKey(Course, on_delete=models.PROTECT, related_name="announcements")
    title = models.CharField(max_length=200)
    body = models.TextField(max_length=5000)
    is_pinned = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)  # soft delete
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="announcements_posted"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-is_pinned", "-created_at"]

    def __str__(self):
        return f"{self.course.code} - {self.title}"
