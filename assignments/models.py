"""Assignments and immutable file submissions with receipts."""
from django.conf import settings
from django.db import models

from core.models import File
from courses.models import Course

GRACE_SECONDS = 60  # submissions stay open this long past the deadline


class Assignment(models.Model):
    course = models.ForeignKey(Course, on_delete=models.PROTECT, related_name="assignments")
    title = models.CharField(max_length=200)
    instructions = models.TextField(blank=True)
    max_score = models.PositiveIntegerField(default=20)
    due_at = models.DateTimeField()  # UTC
    allowed_ext = models.CharField(max_length=100, default="pdf")
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="assignments_created"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["due_at"]

    def __str__(self):
        return f"{self.course.code} — {self.title}"


class Submission(models.Model):
    """One immutable row per attempt. Scores live here until the gradebook
    slice moves raw scores into grade items; totals are computed at read."""

    assignment = models.ForeignKey(Assignment, on_delete=models.PROTECT, related_name="submissions")
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="submissions"
    )
    attempt_no = models.PositiveIntegerField()
    file = models.ForeignKey(File, on_delete=models.PROTECT, related_name="+")
    note = models.TextField(blank=True, max_length=1000)
    is_late = models.BooleanField(default=False)
    submitted_at = models.DateTimeField(auto_now_add=True)
    score = models.PositiveIntegerField(null=True, blank=True)
    score_note = models.TextField(blank=True, max_length=500)
    graded_at = models.DateTimeField(null=True, blank=True)
    graded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.PROTECT, related_name="submissions_graded",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["assignment", "student", "attempt_no"], name="uniq_submission_attempt"
            )
        ]
        ordering = ["submitted_at"]

    def __str__(self):
        return f"{self.assignment_id}/{self.student_id} attempt {self.attempt_no}"
