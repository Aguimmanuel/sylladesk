"""Lecture materials (FR-07–09). Bytes live in core.File via core.storage."""
from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from core.models import File

from courses.models import Course


class Material(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="materials")
    title = models.CharField(max_length=200)
    week_no = models.PositiveIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(52)]
    )
    file = models.ForeignKey(File, on_delete=models.PROTECT, related_name="materials")
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL
    )
    download_count = models.PositiveIntegerField(default=0)
    is_deleted = models.BooleanField(default=False)  # soft delete (FR-08)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["week_no", "title"]

    def __str__(self):
        return f"{self.title} ({self.course.code} W{self.week_no})"
