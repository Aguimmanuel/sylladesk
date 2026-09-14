import io

from django.contrib.auth import get_user_model
from django.core.handlers.exception import response_for_exception
from django.test import TestCase
from django.urls import reverse

from accounts.tests.helpers import make_user
from courses.access import user_role_in_course
from courses.models import Enrollment
from courses.services import claim_roster_entries, import_roster
from courses.tests.helpers import make_course

from core.models import AuditLog

User = get_user_model()
REG = "MOUAU/PSB/26/077001"


def seed():
    lect = make_user(username="togglect@psb.lms", full_name="Toggle Lec", global_role="lecturer")
    c = make_course(lecturer=lect)
    import_roster(c, io.StringIO(f"registration_number,full_name\n{REG},Removable Ruth\n"), actor=None)
    s = make_user(username=REG, reg_no=REG, full_name="Removable Ruth")
    claim_roster_entries(s)
    return c, lect, s


class EnrollmentToggleTests(TestCase):
    def test_remove_denies_access_but_keeps_row(self):
        c, lect, s = seed()
        self.client.force_login(lect)
        r = self.client.post(reverse("courses:enrollment_toggle", args=[c.id, s.id, "remove"]))
        self.assertRedirects(r, reverse("courses:detail", args=[c.id]))
        enr = Enrollment.objects.get(course=c, user=s)
        self.assertFalse(enr.is_active)          # soft: row kept for audit + restore
        self.assertIsNone(user_role_in_course(s, c))   # access gone
        self.assertTrue(AuditLog.objects.filter(action="enrollment.remove").exists())

    def test_restore_returns_access(self):
        c, lect, s = seed()
        self.client.force_login(lect)
        self.client.post(reverse("courses:enrollment_toggle", args=[c.id, s.id, "remove"]))
        r = self.client.post(reverse("courses:enrollment_toggle", args=[c.id, s.id, "restore"]))
        self.assertRedirects(r, reverse("courses:detail", args=[c.id]))
        self.assertEqual(user_role_in_course(s, c), "student")
        self.assertTrue(AuditLog.objects.filter(action="enrollment.restore").exists())

    def test_student_cannot_toggle(self):
        c, lect, s = seed()
        self.client.force_login(s)
        r = self.client.post(reverse("courses:enrollment_toggle", args=[c.id, s.id, "remove"]))
        self.assertRedirects(r, reverse("courses:detail", args=[c.id]))
        self.assertTrue(Enrollment.objects.get(course=c, user=s).is_active)  # unchanged

    def test_removed_student_loses_course_page(self):
        c, lect, s = seed()
        self.client.force_login(lect)
        self.client.post(reverse("courses:enrollment_toggle", args=[c.id, s.id, "remove"]))
        self.client.force_login(s)
        r = self.client.get(reverse("courses:detail", args=[c.id]), follow=True)
        self.assertContains(r, "not enrolled in this course")
