"""The custom User — must exist before the first migrate (AUTH_USER_MODEL).

Global role enum (research section 5): admin / lecturer / student.
Course-level roles live in courses.Enrollment (Phase 2), NOT here.
"""
from django.contrib.auth.base_user import AbstractBaseUser
from django.contrib.auth.models import PermissionsMixin, UserManager
from django.db import models


class User(AbstractBaseUser, PermissionsMixin):
    class GlobalRole(models.TextChoices):
        ADMIN = "admin", "Admin"
        LECTURER = "lecturer", "Lecturer"
        STUDENT = "student", "Student"

    # Students: username = normalized registration number (FR-33, Q-F).
    # Staff: username = email.
    username = models.CharField(max_length=64, unique=True)
    email = models.EmailField(unique=True, null=True, blank=True)
    reg_no = models.CharField(  # students only; claimed from a roster at signup
        max_length=32, unique=True, null=True, blank=True, db_index=True
    )
    full_name = models.CharField(max_length=120)
    global_role = models.CharField(
        max_length=16, choices=GlobalRole.choices, default=GlobalRole.STUDENT
    )
    # FR-01: operator-created accounts start flagged; they can't do anything
    # until they set their own password (enforced by accounts.middleware).
    must_reset_password = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)  # /admin access (admins only)

    objects = UserManager()

    USERNAME_FIELD = "username"
    REQUIRED_FIELDS = ["full_name"]

    class Meta:
        indexes = [models.Index(fields=["global_role"])]

    def __str__(self):
        return f"{self.full_name} ({self.username})"

    @property
    def is_admin_role(self):
        return self.global_role == self.GlobalRole.ADMIN

    @property
    def is_lecturer_role(self):
        return self.global_role == self.GlobalRole.LECTURER

    @property
    def is_student_role(self):
        return self.global_role == self.GlobalRole.STUDENT
