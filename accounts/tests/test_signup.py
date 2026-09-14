import io

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from accounts.tests.helpers import make_user
from courses.services import import_roster
from courses.tests.helpers import make_course
from courses.models import Enrollment, RosterEntry

User = get_user_model()
REG = "MOUAU/PSB/26/012345"          # real department format (school/dept/year/number)
ROSTER = ("registration_number,full_name\n"
          f"{REG},Ada Obi\n"
          "MOUAU/PSB/26/012346,\n")


def seed(course=None):
    course = course or make_course(code="PSB 413")
    import_roster(course, io.StringIO(ROSTER), actor=None)
    return course


class SignupTests(TestCase):
    def test_full_success_with_autoenroll_and_claim(self):
        c1 = seed()
        c2 = make_course(code="PSB 414")  # e.g. carry-over student listed by two lecturers
        import_roster(c2, io.StringIO(f"registration_number,full_name\n{REG},Ada Obi\n"), actor=None)
        r = self.client.post(reverse("accounts:signup"), {
            "reg_no": f" {REG.lower()} ", "full_name": "ada obi",   # messy but matching
            "email": "ada.obi@example.com",
            "password1": "sensible-password-1", "password2": "sensible-password-1",
        })
        self.assertRedirects(r, reverse("home"), fetch_redirect_response=False)
        u = User.objects.get(username=REG)
        self.assertEqual(u.reg_no, REG)  # case/space-normalized, slashes kept
        self.assertEqual(u.email, "ada.obi@example.com")
        self.assertEqual(u.global_role, "student")
        self.assertEqual(Enrollment.objects.filter(user=u).count(), 2)
        self.assertTrue(RosterEntry.objects.filter(reg_no=REG, claimed_by=u).exists())

    def test_unlisted_reg_rejected(self):
        seed()
        r = self.client.post(reverse("accounts:signup"), {
            "reg_no": "MOUAU/PSB/26/099999", "full_name": "Ghost",
            "email": "ghost@example.com",
            "password1": "sensible-password-1", "password2": "sensible-password-1",
        })
        self.assertContains(r, "not on any course roster")
        self.assertEqual(User.objects.filter(global_role="student").count(), 0)

    def test_double_claim_rejected(self):
        seed()
        data = {"reg_no": REG, "full_name": "Ada Obi", "email": "ada.obi@example.com",
                "password1": "sensible-password-1", "password2": "sensible-password-1"}
        self.client.post(reverse("accounts:signup"), data)
        self.client.logout()  # second attempt must come from a fresh anonymous visitor
        r = self.client.post(reverse("accounts:signup"), data)
        self.assertContains(r, "already been registered")
        self.assertEqual(User.objects.filter(global_role="student").count(), 1)

    def test_duplicate_email_rejected(self):
        seed()
        data = {"reg_no": REG, "full_name": "Ada Obi", "email": "ada.obi@example.com",
                "password1": "sensible-password-1", "password2": "sensible-password-1"}
        self.client.post(reverse("accounts:signup"), data)
        self.client.logout()
        # MOUAU/PSB/26/012346 is already on the roster (nameless row) — a second
        # student claiming it while reusing Ada's email must hit the email check.
        r = self.client.post(reverse("accounts:signup"), {
            "reg_no": "MOUAU/PSB/26/012346", "full_name": "Second Student",
            "email": "ADA.OBI@EXAMPLE.COM",  # same address, different case
            "password1": "sensible-password-1", "password2": "sensible-password-1",
        })
        self.assertContains(r, "already in use")
        self.assertEqual(User.objects.filter(global_role="student").count(), 1)

    def test_name_mismatch_rejected(self):
        seed()
        r = self.client.post(reverse("accounts:signup"), {
            "reg_no": REG, "full_name": "Ada Bello",
            "email": "ada.obi@example.com",
            "password1": "sensible-password-1", "password2": "sensible-password-1",
        })
        self.assertContains(r, "does not match the roster")
        self.assertEqual(User.objects.filter(global_role="student").count(), 0)

    def test_short_password_rejected(self):
        seed()
        r = self.client.post(reverse("accounts:signup"), {
            "reg_no": REG, "full_name": "Ada Obi",
            "email": "ada.obi@example.com",
            "password1": "short9", "password2": "short9",
        })
        self.assertEqual(User.objects.filter(global_role="student").count(), 0)

    def test_five_digit_reg_numbers_work(self):
        """Owner clarification 2026-09-13: the tail can be 5 OR 6 digits — the
        system never parses digits, so both must work, and a zero-padded
        6-digit sibling must be a different account, not a collision."""
        c = seed()
        import_roster(c, io.StringIO(
            "registration_number,full_name\nMOUAU/PSB/26/04321,Five Digit\n"), actor=None)
        r = self.client.post(reverse("accounts:signup"), {
            "reg_no": "MOUAU/PSB/26/04321", "full_name": "Five Digit",
            "email": "five@example.com",
            "password1": "sensible-password-1", "password2": "sensible-password-1",
        })
        self.assertRedirects(r, reverse("home"), fetch_redirect_response=False)
        self.assertTrue(User.objects.filter(reg_no="MOUAU/PSB/26/04321").exists())
        # zero-padded 6-digit sibling = different person, also fine
        import_roster(c, io.StringIO(
            "registration_number,full_name\nMOUAU/PSB/26/004321,Six Digit\n"), actor=None)
        self.client.logout()
        r = self.client.post(reverse("accounts:signup"), {
            "reg_no": "MOUAU/PSB/26/004321", "full_name": "Six Digit",
            "email": "six@example.com",
            "password1": "sensible-password-1", "password2": "sensible-password-1",
        })
        self.assertRedirects(r, reverse("home"), fetch_redirect_response=False)
        self.assertEqual(User.objects.filter(global_role="student").count(), 2)

    def test_signup_throttle(self):
        seed()
        from accounts.models import SignupAttempt
        from django.utils import timezone
        now = timezone.now()
        for i in range(20):
            SignupAttempt.objects.create(ip="127.0.0.1", created_at=now)
        r = self.client.get(reverse("accounts:signup"))
        self.assertEqual(r.status_code, 200)  # page fine
        r = self.client.post(reverse("accounts:signup"), {
            "reg_no": REG, "full_name": "Ada Obi", "email": "ada.obi@example.com",
            "password1": "sensible-password-1", "password2": "sensible-password-1",
        })
        self.assertRedirects(r, reverse("accounts:login"), fetch_redirect_response=False)
        self.assertEqual(User.objects.filter(global_role="student").count(), 0)

    def test_inactive_roster_number_cannot_sign_up(self):
        c = seed()
        import_roster(c, io.StringIO(
            "registration_number,full_name\nMOUAU/PSB/25/018001,Old Row\n"), actor=None)
        import_roster(c, io.StringIO("registration_number,full_name\n"), actor=None)  # deactivate all
        r = self.client.post(reverse("accounts:signup"), {
            "reg_no": "MOUAU/PSB/26/012346", "full_name": "Tunde",
            "email": "tunde@example.com",
            "password1": "sensible-password-1", "password2": "sensible-password-1",
        })
        self.assertContains(r, "not on any course roster")

    def test_new_course_roster_claims_at_list_view(self):
        """Owner live finding 2026-09-14: roster uploaded AFTER signup must still
        reach the student - claimed on their next visit to My courses."""
        seed()
        self.client.post(reverse("accounts:signup"), {
            "reg_no": REG, "full_name": "Ada Obi", "email": "ada.obi@example.com",
            "password1": "sensible-password-1", "password2": "sensible-password-1"})
        c2 = make_course(code="PSB 415")
        import_roster(c2, io.StringIO(f"registration_number,full_name\n{REG},Ada Obi\n"), actor=None)
        self.client.logout()
        self.client.post(reverse("accounts:login"),
                         {"username": REG, "password": "sensible-password-1"})
        r = self.client.get(reverse("courses:list"))
        self.assertContains(r, "PSB 415")
        u = User.objects.get(username=REG)
        self.assertTrue(Enrollment.objects.filter(user=u, course=c2).exists())
        self.assertTrue(RosterEntry.objects.filter(reg_no=REG, course=c2, claimed_by=u).exists())
