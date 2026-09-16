import io
import json
import re
from unittest import mock

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.tests.helpers import make_user

User = get_user_model()
EMAIL = "ada.obi@example.com"


def make_ada(**extra):
    u = make_user(username="MOUAU/PSB/26/088001", reg_no="MOUAU/PSB/26/088001",
                  full_name="Ada Obi", password="old-password-99", **extra)
    u.email = EMAIL
    u.save()
    return u


class PasswordResetTests(TestCase):
    def test_login_hides_link_when_unconfigured(self):
        r = self.client.get(reverse("accounts:login"))
        self.assertNotContains(r, "Forgot password?")

    @override_settings(EMAIL_HOST_USER="sender@example.com")
    def test_login_shows_link_when_configured(self):
        r = self.client.get(reverse("accounts:login"))
        self.assertContains(r, "Forgot password?")

    @override_settings(EMAIL_HOST_USER="sender@example.com")
    def test_existing_email_gets_link(self):
        make_ada()
        r = self.client.post(reverse("accounts:password_reset"), {"email": EMAIL})
        self.assertRedirects(r, reverse("accounts:password_reset_done"))
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("SyllaDesk", mail.outbox[0].subject)
        self.assertIn("/accounts/password/reset/", mail.outbox[0].body)

    @override_settings(EMAIL_HOST_USER="sender@example.com")
    def test_unknown_email_same_response_no_mail(self):
        r = self.client.post(reverse("accounts:password_reset"), {"email": "ghost@example.com"})
        self.assertRedirects(r, reverse("accounts:password_reset_done"))  # identical, no enumeration
        self.assertEqual(len(mail.outbox), 0)

    @override_settings(EMAIL_HOST_USER="sender@example.com")
    def test_full_flow_sets_new_password(self):
        u = make_ada()
        self.client.post(reverse("accounts:password_reset"), {"email": EMAIL})
        m = re.search(r"/accounts/password/reset/([\w-]+)/([\w-]+)/", mail.outbox[0].body)
        confirm = reverse("accounts:password_reset_confirm", args=[m.group(1), m.group(2)])
        r = self.client.get(confirm)
        # stock Django: valid token redirects to the ".../set-password/" form URL
        self.assertEqual(r.status_code, 302)
        set_pw_url = r.url  # capture, then GET and POST the same URL
        r = self.client.get(set_pw_url)
        self.assertContains(r, "Set a new password")
        r = self.client.post(set_pw_url, {"new_password1": "brand-new-password-7",
                                          "new_password2": "brand-new-password-7"})
        self.assertRedirects(r, reverse("accounts:password_reset_complete"))
        self.assertTrue(User.objects.get(pk=u.pk).check_password("brand-new-password-7"))
        self.assertFalse(User.objects.get(pk=u.pk).check_password("old-password-99"))
        # verify via the login FORM (axes middleware requires a request object)
        self.client.logout()
        r = self.client.post(reverse("accounts:login"),
                             {"username": u.username, "password": "brand-new-password-7"})
        self.assertRedirects(r, reverse("home"), fetch_redirect_response=False)  # home routes students on
        self.client.logout()  # old-password attempt must come from a logged-out visitor
        r = self.client.post(reverse("accounts:login"),
                             {"username": u.username, "password": "old-password-99"})
        self.assertContains(r, "Wrong username or password")

    @override_settings(EMAIL_HOST_USER="sender@example.com")
    def test_reset_clears_forced_flag(self):
        u = make_ada(must_reset_password=True)
        self.client.post(reverse("accounts:password_reset"), {"email": EMAIL})
        m = re.search(r"/accounts/password/reset/([\w-]+)/([\w-]+)/", mail.outbox[0].body)
        confirm = reverse("accounts:password_reset_confirm", args=[m.group(1), m.group(2)])
        r = self.client.get(confirm)
        self.client.post(r.url, {"new_password1": "brand-new-password-7",
                                 "new_password2": "brand-new-password-7"})
        self.assertFalse(User.objects.get(pk=u.pk).must_reset_password)

    @override_settings(EMAIL_HOST_USER="sender@example.com")
    def test_throttled_after_10_requests(self):
        make_ada()
        for _ in range(10):
            self.client.post(reverse("accounts:password_reset"), {"email": EMAIL})
        r = self.client.post(reverse("accounts:password_reset"), {"email": EMAIL})
        self.assertRedirects(r, reverse("accounts:login"), fetch_redirect_response=False)
        self.assertEqual(len(mail.outbox), 10)

    def test_done_page_honest_when_sending_not_configured(self):
        """Without a configured sender, the done page must say no mail went out."""
        make_ada()
        r = self.client.post(reverse("accounts:password_reset"), {"email": EMAIL})
        r = self.client.get(reverse("accounts:password_reset_done"))
        self.assertContains(r, "not set up on this deployment")

    @override_settings(EMAIL_HOST_USER="sender@example.com")
    def test_done_page_promises_mail_when_configured(self):
        make_ada()
        self.client.post(reverse("accounts:password_reset"), {"email": EMAIL})
        r = self.client.get(reverse("accounts:password_reset_done"))
        self.assertContains(r, "a reset link is on its way")
        self.assertNotContains(r, "not set up on this deployment")


class FailingMailBackend:
    """Stands in for a blocked/broken SMTP path (e.g. Render free tier).
    Django instantiates backends as klass(fail_silently=False) - hence __init__."""

    def __init__(self, fail_silently=False, **kwargs):
        self.fail_silently = fail_silently

    def send_messages(self, email_messages):
        raise OSError("simulated outbound SMTP failure")


class MailOutageTests(TestCase):
    @override_settings(EMAIL_BACKEND="accounts.tests.test_password_reset.FailingMailBackend",
                       EMAIL_HOST_USER="sender@example.com")
    def test_outage_degrades_gracefully_no_500(self):
        """An SMTP outage must degrade to a friendly redirect and message — never
        a 500, never a false success page."""
        make_ada()
        r = self.client.post(reverse("accounts:password_reset"), {"email": EMAIL})
        self.assertEqual(r.status_code, 302)  # graceful, not a 500
        self.assertRedirects(r, reverse("accounts:login"), fetch_redirect_response=False)
        r = self.client.get(reverse("accounts:login"))
        self.assertContains(r, "could not send the reset email")


class AppsScriptMailTests(TestCase):
    """Mail goes over HTTPS to the Apps Script Web App."""

    @override_settings(EMAIL_BACKEND="core.mail_backends.AppsScriptMailBackend",
                       APPS_SCRIPT_MAIL_URL="https://script.example/exec",
                       APPS_SCRIPT_MAIL_TOKEN="tok")
    def test_backend_posts_and_confirms(self):
        make_ada()
        with mock.patch("core.mail_backends.AppsScriptMailBackend._post") as post:
            post.return_value = True
            r = self.client.post(reverse("accounts:password_reset"), {"email": EMAIL})
            self.assertRedirects(r, reverse("accounts:password_reset_done"))
            post.assert_called_once()
            kwargs = post.call_args.kwargs
            self.assertEqual(kwargs["to"], EMAIL)
            self.assertIn("SyllaDesk", kwargs["subject"])
            self.assertIn("/accounts/password/reset/", kwargs["text"])

    @override_settings(EMAIL_BACKEND="core.mail_backends.AppsScriptMailBackend",
                       APPS_SCRIPT_MAIL_URL="https://script.example/exec",
                       APPS_SCRIPT_MAIL_TOKEN="tok")
    def test_backend_failure_surfaces_to_student(self):
        make_ada()
        with mock.patch("core.mail_backends.AppsScriptMailBackend._post") as post:
            post.side_effect = OSError("script unreachable")
            r = self.client.post(reverse("accounts:password_reset"), {"email": EMAIL})
            self.assertRedirects(r, reverse("accounts:login"), fetch_redirect_response=False)
            r = self.client.get(reverse("accounts:login"))
            self.assertContains(r, "could not send the reset email")

    @override_settings(APPS_SCRIPT_MAIL_URL="https://script.example/exec",
                       APPS_SCRIPT_MAIL_TOKEN="sekret")
    def test_payload_carries_token_and_fields(self):
        from core import mail_backends
        captured = {}

        class FakeResp(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        def fake_urlopen(req, timeout=None):
            captured["url"] = req.full_url
            captured["data"] = req.data
            return FakeResp(b'{"ok": true}')

        be = mail_backends.AppsScriptMailBackend()
        with mock.patch("urllib.request.urlopen", fake_urlopen):
            be._post(to="a@b.c", subject="Hi", text="Body")
        sent = json.loads(captured["data"])
        self.assertEqual(captured["url"], "https://script.example/exec")
        self.assertEqual(sent["token"], "sekret")
        self.assertEqual(sent["to"], "a@b.c")

    @override_settings(EMAIL_BACKEND="core.mail_backends.AppsScriptMailBackend",
                       APPS_SCRIPT_MAIL_URL="https://script.example/exec",
                       APPS_SCRIPT_MAIL_TOKEN="tok")
    def test_script_error_payload_raises(self):
        """An HTML 'please sign in' page or an error JSON must NOT count as sent."""
        from core import mail_backends
        be = mail_backends.AppsScriptMailBackend()
        with mock.patch("urllib.request.urlopen") as urlopen:
            urlopen.return_value.__enter__.return_value.read.return_value = (
                b"<html>Sign in - Google Accounts</html>")
            with self.assertRaises(OSError):
                be._post(to="a@b.c", subject="Hi", text="Body")
