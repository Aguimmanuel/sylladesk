from datetime import timedelta

from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse

from .helpers import make_user


@override_settings(AXES_FAILURE_LIMIT=3, AXES_COOLOFF_TIME=timedelta(minutes=15))
class LockoutTests(TestCase):
    def test_locks_after_limit_and_reset_command_recovers(self):
        make_user(username="student1", password="sensible-password-1")
        url = reverse("accounts:login")
        for _ in range(3):
            self.client.post(url, {"username": "student1", "password": "wrong"})
        # 4th attempt: axes blocks the request even with the CORRECT password
        r = self.client.post(url, {"username": "student1", "password": "sensible-password-1"})
        self.assertIn(r.status_code, (403, 429))
        # operator-side recovery: the axes reset command (runbook section 6)
        call_command("axes_reset_username", "student1", verbosity=0)
        r = self.client.post(url, {"username": "student1", "password": "sensible-password-1"})
        self.assertRedirects(r, reverse("home"), fetch_redirect_response=False)
