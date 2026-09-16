"""Courses, enrollments, and the authenticated roster.

A RosterEntry must exist and be unclaimed before a student can create an
account. Claiming marks the entry and creates the enrollment in a single
transaction.
"""
from django.conf import settings
from django.db import models


class Course(models.Model):
    class Semester(models.TextChoices):
        FIRST = "first", "First"
        SECOND = "second", "Second"

    code = models.CharField(max_length=20)
    title = models.CharField(max_length=200)
    session = models.CharField(max_length=12, help_text='e.g. "2025/2026"')
    semester = models.CharField(max_length=10, choices=Semester.choices)
    lecturer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="courses_taught"
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("code", "session")]
        ordering = ["code"]

    def clean(self):
        """Normalize code and session; the unique constraint is case-sensitive."""
        self.code = " ".join((self.code or "").split()).upper()
        self.session = " ".join((self.session or "").split())

    def __str__(self):
        return f"{self.code} — {self.title} ({self.session})"


class Enrollment(models.Model):
    class Role(models.TextChoices):
        LECTURER = "lecturer", "Lecturer"
        TA = "ta", "TA"
        STUDENT = "student", "Student"

    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="enrollments")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="enrollments"
    )
    role_in_course = models.CharField(max_length=10, choices=Role.choices, default=Role.STUDENT)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("course", "user")]

    def __str__(self):
        return f"{self.user} in {self.course} ({self.role_in_course})"


class RosterEntry(models.Model):
    """One authenticated registration number for one course."""

    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="roster_entries")
    reg_no = models.CharField(max_length=50, db_index=True)
    full_name = models.CharField(max_length=120, blank=True)  # optional; enables name-match
    claimed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="roster_claims",
    )
    claimed_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("course", "reg_no")]
        ordering = ["reg_no"]

    def __str__(self):
        return f"{self.reg_no} @ {self.course.code}"
