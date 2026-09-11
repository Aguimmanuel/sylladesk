from django.test import TestCase
from django.urls import reverse

from .helpers import make_user


class LoginFlowTests(TestCase):
    def test_login_page_renders(self):
        r = self.client.get(reverse("accounts:login"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Log in")

    def test_login_success_redirects_home(self):
        make_user(username="student1", password="sensible-password-1")
        r = self.client.post(reverse("accounts:login"),
                             {"username": "student1", "password": "sensible-password-1"})
        self.assertRedirects(r, reverse("home"), fetch_redirect_response=False)

    def test_login_wrong_password_shows_error(self):
        make_user(username="student1", password="sensible-password-1")
        r = self.client.post(reverse("accounts:login"),
                             {"username": "student1", "password": "wrong-password"})
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Wrong username or password")

    def test_anonymous_home_redirects_to_login(self):
        r = self.client.get(reverse("home"))
        self.assertRedirects(r, "/accounts/login/?next=/", fetch_redirect_response=False)

    def test_logout_post_then_home_requires_login(self):
        make_user(username="student1", password="sensible-password-1")
        self.client.post(reverse("accounts:login"),
                         {"username": "student1", "password": "sensible-password-1"})
        r = self.client.post(reverse("accounts:logout"))
        self.assertEqual(r.status_code, 302)
        r = self.client.get(reverse("home"))
        self.assertEqual(r.status_code, 302)


class HomeRoutingTests(TestCase):
    def test_student_gets_placeholder_home(self):
        make_user(username="student1", global_role="student")
        self.client.post(reverse("accounts:login"),
                         {"username": "student1", "password": "sensible-password-1"})
        r = self.client.get(reverse("home"))
        self.assertContains(r, "student")

    def test_admin_redirects_to_admin_site(self):
        u = make_user(username="owner@psb.lms", global_role="admin")
        u.is_staff = True
        u.save()
        self.client.post(reverse("accounts:login"),
                         {"username": "owner@psb.lms", "password": "sensible-password-1"})
        r = self.client.get(reverse("home"))
        self.assertRedirects(r, reverse("admin:index"), fetch_redirect_response=False)
