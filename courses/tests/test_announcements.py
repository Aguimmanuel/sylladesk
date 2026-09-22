from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.tests.helpers import make_user
from announcements.models import Announcement
from assessments.services import close_test, release_results
from assessments.tests.helpers import (add_mcq, enroll, make_student_enrolled,
                                       make_test, open_test)
from assignments.models import Assignment, Submission
from assignments.tests.helpers import PDF_BYTES, make_assignment
from core.models import AuditLog, File, FileBlob
from courses.tests.helpers import make_course


class AnnouncementTests(TestCase):
    def setUp(self):
        self.lecturer = make_user(username="annlect@psb.lms", global_role="lecturer")
        self.course = make_course(lecturer=self.lecturer)
        self.student = make_student_enrolled(reg="MOUAU/PSB/26/110001")
        enroll(self.course, self.student)

    def _post(self, title, body="Hello class.", pin=False):
        self.client.force_login(self.lecturer)
        return self.client.post(reverse("announcements:create", args=[self.course.id]),
                                {"title": title, "body": body,
                                 "is_pinned": "on" if pin else ""})

    def test_post_then_students_see_it_pinned_first(self):
        self._post("Regular news")
        self._post("Exam moves", body="Room changed.", pin=True)
        self.client.force_login(self.student)
        r = self.client.get(reverse("courses:detail", args=[self.course.id]))
        self.assertContains(r, "Exam moves")
        self.assertContains(r, "Room changed.")
        self.assertContains(r, "Pinned")
        items = r.context["announcements"]
        self.assertEqual(items[0].title, "Exam moves")  # pinned first, then newest
        self.assertEqual(items[1].title, "Regular news")
        self.assertTrue(AuditLog.objects.filter(action="announcement.create").exists())

    def test_students_get_no_compose_form_and_cannot_post(self):
        self.client.force_login(self.student)
        r = self.client.get(reverse("courses:detail", args=[self.course.id]))
        self.assertNotContains(r, "Post announcement")
        r = self.client.post(reverse("announcements:create", args=[self.course.id]),
                             {"title": "x", "body": "y"})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(Announcement.objects.count(), 0)

    def test_long_body_refused(self):
        self._post("Too long", body="x" * 5001)
        self.assertEqual(Announcement.objects.count(), 0)

    def test_edit_updates_title_body_and_pin(self):
        self._post("Draft news", body="first")
        a = Announcement.objects.get()
        self.client.force_login(self.lecturer)
        r = self.client.get(reverse("announcements:edit", args=[self.course.id, a.id]))
        self.assertContains(r, "Draft news")
        r = self.client.post(reverse("announcements:edit", args=[self.course.id, a.id]),
                             {"title": "Final news", "body": "updated", "is_pinned": "on"},
                             follow=True)
        self.assertContains(r, "Final news")
        a.refresh_from_db()
        self.assertTrue(a.is_pinned)
        self.assertEqual(a.body, "updated")

    def test_delete_goes_to_trash_and_restore_and_purge(self):
        self._post("Temp note")
        a = Announcement.objects.get()
        self.client.force_login(self.lecturer)
        self.client.post(reverse("announcements:delete", args=[self.course.id, a.id]))
        r = self.client.get(reverse("courses:detail", args=[self.course.id]))
        self.assertNotContains(r, "Temp note")
        r = self.client.get(reverse("courses:trash", args=[self.course.id]))
        self.assertContains(r, "Temp note")  # sitting in the trash
        self.client.post(reverse("courses:trash_restore",
                                 args=[self.course.id, "announcement", a.id]))
        r = self.client.get(reverse("courses:detail", args=[self.course.id]))
        self.assertContains(r, "Temp note")  # back on the course page
        self.client.post(reverse("announcements:delete", args=[self.course.id, a.id]))
        r = self.client.post(reverse("courses:trash_delete",
                                     args=[self.course.id, "announcement", a.id]))
        self.assertEqual(r.status_code, 302)
        self.assertFalse(Announcement.objects.filter(pk=a.pk).exists())  # gone for good


class DueSoonTests(TestCase):
    def setUp(self):
        self.lecturer = make_user(username="duelect@psb.lms", global_role="lecturer")
        self.course = make_course(lecturer=self.lecturer)
        self.student = make_student_enrolled(reg="MOUAU/PSB/26/110002")
        enroll(self.course, self.student)

    def _submit(self, assignment):
        FileBlob.objects.create(key=f"ds-{assignment.id}", data=PDF_BYTES)
        f = File.objects.create(
            storage_key=f"ds-{assignment.id}", original_name="s.pdf",
            mime="application/pdf", size_bytes=len(PDF_BYTES), sha256="2" * 64,
        )
        Submission.objects.create(assignment=assignment, student=self.student,
                                  attempt_no=1, file=f)

    def test_due_assignment_appears_then_disappears_after_submission(self):
        make_assignment(self.course, due=timezone.now() + timedelta(days=3))
        self.client.force_login(self.student)
        r = self.client.get(reverse("courses:detail", args=[self.course.id]))
        self.assertContains(r, "Due in the next 7 days")
        self.assertContains(r, "Cell Division Report")
        self._submit(Assignment.objects.get())
        r = self.client.get(reverse("courses:detail", args=[self.course.id]))
        self.assertNotContains(r, "Due in the next 7 days")

    def test_far_future_assignment_never_shows(self):
        make_assignment(self.course, due=timezone.now() + timedelta(days=20))
        self.client.force_login(self.student)
        r = self.client.get(reverse("courses:detail", args=[self.course.id]))
        self.assertNotContains(r, "Due in the next 7 days")

    def test_live_test_shows_and_leaves_when_submitted(self):
        t = make_test(self.course, n_obj=1)
        add_mcq(t)
        open_test(t)
        self.client.force_login(self.student)
        r = self.client.get(reverse("courses:detail", args=[self.course.id]))
        self.assertContains(r, "Live now")
        from assessments.services import start_attempt, submit
        a = start_attempt(t, student=self.student)
        submit(a)
        r = self.client.get(reverse("courses:detail", args=[self.course.id]))
        self.assertNotContains(r, "Live now")

    def test_closed_test_not_shown(self):
        t = make_test(self.course, n_obj=1)
        add_mcq(t)
        open_test(t)
        close_test(t, actor=self.lecturer)
        self.client.force_login(self.student)
        r = self.client.get(reverse("courses:detail", args=[self.course.id]))
        self.assertNotContains(r, "Live now")

    def test_staff_never_sees_the_block(self):
        make_assignment(self.course, due=timezone.now() + timedelta(days=3))
        self.client.force_login(self.lecturer)
        r = self.client.get(reverse("courses:detail", args=[self.course.id]))
        self.assertNotContains(r, "Due in the next 7 days")
