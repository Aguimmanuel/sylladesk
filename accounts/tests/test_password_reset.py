import re

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
        set_pw_url = r.url                       # capture, then GET and POST the same URL
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
        self.assertRedirects(r, reverse("home"), fetch_redirect_response=False)  # home then routes students on
        self.client.logout()  # the old-password attempt must come from a logged-out visitor
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
