"""Dev convenience: idempotent demo accounts. NOT for production use."""
import os

from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model

User = get_user_model()


class Command(BaseCommand):
    help = "Create/refresh demo admin + lecturer accounts (idempotent)."

    def handle(self, *args, **options):
        admin_email = os.environ.get("SEED_ADMIN_EMAIL", "owner@psb.lms")
        admin_pw = os.environ.get("SEED_ADMIN_PASSWORD", "demo-admin-change-me-1")
        admin, created = User.objects.update_or_create(
            username=admin_email,
            defaults={
                "email": admin_email,
                "full_name": "Platform Owner",
                "global_role": User.GlobalRole.ADMIN,
                "is_staff": True,
                "is_superuser": True,
                "must_reset_password": False,
            },
        )
        admin.set_password(admin_pw)
        admin.save()

        lect, lect_created = User.objects.get_or_create(
            username="advisor@psb.lms",
            defaults={
                "email": "advisor@psb.lms",
                "full_name": "Demo Lecturer",
                "global_role": User.GlobalRole.LECTURER,
                "must_reset_password": False,
            },
        )
        if lect_created:
            lect.set_password("demo-lecturer-change-me-1")
            lect.save()

        self.stdout.write(self.style.SUCCESS(
            f"admin: {admin_email} / {admin_pw} ({'created' if created else 'updated'})\n"
            f"lecturer: advisor@psb.lms / demo-lecturer-change-me-1 ({'created' if lect_created else 'exists'})"
        ))
