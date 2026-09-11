"""Ensure the platform owner admin exists (idempotent, env-driven).

Free hosting has no interactive shell, so the first admin must be created by the
deploy itself. This command runs in the build and only enforces the ONE owner
defined by env vars — unlike seed_demo (dev-only, never on production).

Env vars:
  OWNER_USERNAME  (required)  e.g. owner@sylladesk.app
  OWNER_EMAIL     (optional)
  OWNER_PASSWORD  (required)  long + unique — this is the keys to the kingdom
"""
import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from core.auditing import audit

User = get_user_model()


class Command(BaseCommand):
    help = "Create the owner admin if missing (never touches an existing one)."

    def handle(self, *args, **options):
        username = os.environ.get("OWNER_USERNAME")
        email = os.environ.get("OWNER_EMAIL", "")
        password = os.environ.get("OWNER_PASSWORD")
        if not username or not password:
            raise CommandError("OWNER_USERNAME and OWNER_PASSWORD must be set.")
        if len(password) < 12:
            raise CommandError("OWNER_PASSWORD must be at least 12 characters.")
        exists = User.objects.filter(username=username).exists()
        if exists:
            self.stdout.write(f"Owner admin exists: {username} (unchanged)")
            return
        user = User(
            username=username,
            email=email,
            full_name="Platform Owner",
            global_role=User.GlobalRole.ADMIN,
            is_staff=True,
            is_superuser=True,
        )
        user.set_password(password)
        user.save()
        audit(actor=user, action="owner.created", obj=user)
        self.stdout.write(self.style.SUCCESS(f"Owner admin created: {username}"))