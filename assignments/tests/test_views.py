from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from courses.tests.helpers import make_course

from ..models import Submission
from ..services import submit_assignment
from .helpers import PDF_BYTES, enroll, make_assignment, make_student, upload


def seed():
    a = make_assignment()
    s = make_student()
    enroll(a.course, s)
    return a, a.course.lecturer, s


class ViewTests(TestCase):
    def test_staff_creates_assignment(self):
        a0, lect, _ = seed()
        self.client.force_login(lect)
        r = self.client.post(reverse("assignments:create", args=[a0.course.id]), {
            "title": "New Work", "instructions": "Read chapter 4",
            "max_score": "15",
            "due_at": (timezone.now() + timezone.timedelta(days=4)).strftime("%Y-%m-%dT%H:%M"),
            "allowed_ext": "pdf"})
        self.assertEqual(Submission.objects.filter(assignment__title="New Work").count(), 0)
        a0.refresh_from_db()
        self.assertTrue(a0.course.assignments.filter(title="New Work").exists())

    def test_student_submits_and_gets_receipt_flash(self):
        a, lect, s = seed()
        self.client.force_login(s)
        r = self.client.post(reverse("assignments:submit", args=[a.course.id, a.id]),
                             {"submission_file": upload(), "note": ""},
                             follow=True)
        self.assertContains(r, "Receipt")
        self.assertEqual(Submission.objects.filter(assignment=a, student=s).count(), 1)
        self.assertContains(r, "checksum")

    def test_after_grace_submit_refused_with_message(self):
        a = make_assignment(due=timezone.now() - timezone.timedelta(minutes=5))
        s = make_student()
        enroll(a.course, s)
        self.client.force_login(s)
        r = self.client.post(reverse("assignments:submit", args=[a.course.id, a.id]),
                             {"submission_file": upload(), "note": ""}, follow=True)
        self.assertContains(r, "deadline has passed")
        self.assertEqual(Submission.objects.count(), 0)

    def test_staff_grades_via_form(self):
        a, lect, s = seed()
        sub = submit_assignment(a, student=s, uploaded=upload())
        self.client.force_login(lect)
        r = self.client.post(reverse("assignments:grade", args=[a.course.id, a.id, sub.id]),
                             {"score": "18", "score_note": "nice"}, follow=True)
        sub.refresh_from_db()
        self.assertEqual(sub.score, 18)

    def test_download_permissions(self):
        a, lect, s = seed()
        sub = submit_assignment(a, student=s, uploaded=upload())
        other = make_student(reg="MOUAU/PSB/26/060009")
        enroll(a.course, other)
        url = reverse("assignments:submission_download", args=[a.course.id, a.id, sub.id])
        self.client.force_login(s)
        self.assertEqual(self.client.get(url).status_code, 200)
        self.client.force_login(other)
        self.assertEqual(self.client.get(url).status_code, 404)
        self.client.force_login(lect)
        self.assertEqual(self.client.get(url).status_code, 200)

    def test_staff_sees_late_and_missing(self):
        a, lect, s = seed()
        a.due_at = timezone.now() - timezone.timedelta(seconds=30)
        a.save()
        submit_assignment(a, student=s, uploaded=upload())
        make_student(reg="MOUAU/PSB/26/060010")  # exists but not enrolled -> not listed
        missing = make_student(reg="MOUAU/PSB/26/060011")
        enroll(a.course, missing)
        self.client.force_login(lect)
        r = self.client.get(reverse("assignments:detail", args=[a.course.id, a.id]))
        self.assertContains(r, "LATE")
        self.assertContains(r, "missing")
