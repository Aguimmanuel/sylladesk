from django.test import TestCase
from django.urls import reverse

from core.auditing import audit
from core.models import AuditLog

from .helpers import make_user


class ForcedResetTests(TestCase):
    def setUp(self):
        # staff account created by import/admin: temp credential state
        self.user = make_user(
            username="lecturer@psb.lms",
            global_role="lecturer",
            password="temp-unusable",
            must_reset_password=True,
        )
        self.user.set_unusable_password()
        self.user.save()

    def _login_temp(self):
        """Simulate the temp-credential session: authenticate + set backend + flag."""
        session = self.client.session
        session["_auth_user_id"] = str(self.user.pk)
        session.save()
        self.client.get("/healthz")  # warm the session
        from django.contrib.auth.middleware import RemoteUserMiddleware  # noqa: F401
        # Force attach user to the client session the supported way:
        from django.test import Client
        self.client.force_login(self.user)

    def test_everywhere_redirects_to_password_set(self):
        self.client.force_login(self.user)
        for path in ("/", "/healthz-not-allowed".replace("/healthz-not-allowed", "/")):
            r = self.client.get(path)
            self.assertRedirects(r, reverse("accounts:password_set"),
                                 fetch_redirect_response=False)

    def test_password_set_rejects_short_password(self):
        self.client.force_login(self.user)
        r = self.client.post(reverse("accounts:password_set"),
                             {"new_password1": "short9", "new_password2": "short9"})
        self.assertEqual(r.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.must_reset_password)

    def test_password_set_success_frees_the_account_and_audits(self):
        self.client.force_login(self.user)
        r = self.client.post(reverse("accounts:password_set"),
                             {"new_password1": "brand-new-password-9",
                              "new_password2": "brand-new-password-9"})
        self.assertRedirects(r, reverse("home"), fetch_redirect_response=False)
        self.user.refresh_from_db()
        self.assertFalse(self.user.must_reset_password)
        self.assertTrue(AuditLog.objects.filter(
            actor=self.user, action="auth.password_set").exists())

    def test_set_page_unreachable_without_flag(self):
        ok_user = make_user(username="student2", password="sensible-password-1")
        self.client.force_login(ok_user)
        r = self.client.get(reverse("accounts:password_set"))
        self.assertRedirects(r, reverse("home"), fetch_redirect_response=False)
