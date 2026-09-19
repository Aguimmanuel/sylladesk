from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.tests.helpers import make_user
from assessments.services import release_results, save_answer, start_attempt
from assessments.tests.helpers import (add_mcq, add_short, enroll,
                                       make_student_enrolled, make_test, open_test)
from assignments.models import Submission
from assignments.tests.helpers import PDF_BYTES, make_assignment
from core.models import File, FileBlob
from courses.tests.helpers import make_course
from .helpers import make_lecturer


def graded_submission(course, assignment, student, *, score, note=""):
    key = f"gb-{assignment.id}-{student.id}"
    FileBlob.objects.create(key=key, data=PDF_BYTES)
    f = File.objects.create(
        storage_key=key, original_name="sub.pdf", mime="application/pdf",
        size_bytes=len(PDF_BYTES), sha256="0" * 64,
    )
    return Submission.objects.create(
        assignment=assignment, student=student, attempt_no=1, file=f,
        score=score, score_note=note, graded_at=timezone.now(),
    )


class GradebookTests(TestCase):
    def setUp(self):
        self.staff = make_lecturer()
        self.course = make_course(lecturer=self.staff)
        self.alice = make_student_enrolled(reg="MOUAU/PSB/26/090001")
        self.bode = make_student_enrolled(reg="MOUAU/PSB/26/090002")
        enroll(self.course, self.alice)
        enroll(self.course, self.bode)
        # released test worth 2: alice got both, bode did not participate
        self.test = make_test(self.course, n_obj=1, n_short=1, points_per_question=1)
        add_mcq(self.test)
        add_short(self.test, accepted="chlorophyll")
        open_test(self.test)
        a = start_attempt(self.test, student=self.alice)
        save_answer(a, question_id=a.drawn_questions()[0].id, choice="B")
        from assessments.services import advance_section
        advance_section(a)
        save_answer(a, question_id=a.drawn_questions()[-1].id, text="chlorophyll")
        release_results(self.test, actor=self.staff)
        # unreleased test: nobody may see its scores
        self.hidden = make_test(self.course, n_obj=1, title="Hidden Midterm")
        add_mcq(self.hidden)
        open_test(self.hidden)
        h = start_attempt(self.hidden, student=self.alice)
        save_answer(h, question_id=h.drawn_questions()[0].id, choice="B")
        # assignment worth 30: alice graded 24 with a note; bode submitted, unmarked
        self.asg = make_assignment(self.course)
        graded_submission(self.course, self.asg, self.alice, score=24, note="Neat work")
        from assignments.tests.helpers import PDF_BYTES as _  # noqa: F401
        key2 = f"gb-bode-{self.asg.id}"
        FileBlob.objects.create(key=key2, data=PDF_BYTES)
        f2 = File.objects.create(
            storage_key=key2, original_name="b.pdf", mime="application/pdf",
            size_bytes=len(PDF_BYTES), sha256="1" * 64,
        )
        Submission.objects.create(assignment=self.asg, student=self.bode, attempt_no=1, file=f2)

    def test_staff_sees_everyone_and_every_column(self):
        self.client.force_login(self.staff)
        r = self.client.get(reverse("courses:gradebook", args=[self.course.id]))
        self.assertContains(r, self.alice.full_name)
        self.assertContains(r, self.bode.full_name)
        self.assertContains(r, self.test.title)
        self.assertContains(r, self.hidden.title)   # staff see it pre-release
        self.assertContains(r, self.asg.title)
        self.assertContains(r, ">24</strong>")      # alice's marked assignment
        self.assertContains(r, "Not marked")        # bode submitted, unmarked
        self.assertContains(r, "3 of 3 items")      # staff see the pre-release test too
        self.assertContains(r, "max 30")

    def test_student_sees_own_row_only_and_no_unreleased_columns(self):
        self.client.force_login(self.alice)
        r = self.client.get(reverse("courses:gradebook", args=[self.course.id]))
        self.assertContains(r, self.test.title)
        self.assertContains(r, "24")                 # her marked assignment
        self.assertContains(r, "Neat work")          # the lecturer's note (FR-23)
        self.assertNotContains(r, self.hidden.title)  # unreleased: no column at all
        self.assertNotContains(r, self.bode.username)  # classmates never appear
        self.assertContains(r, "2 of 2 items")

    def test_non_participant_sees_dash_never_zero(self):
        self.client.force_login(self.bode)
        r = self.client.get(reverse("courses:gradebook", args=[self.course.id]))
        self.assertContains(r, self.test.title)      # released: visible to all
        self.assertContains(r, "—")                  # dash, not a zero
        self.assertNotContains(r, "<strong>0</strong>")

    def test_release_makes_test_column_appear_for_students(self):
        self.client.force_login(self.bode)
        r = self.client.get(reverse("courses:gradebook", args=[self.course.id]))
        self.assertNotContains(r, self.hidden.title)
        release_results(self.hidden, actor=self.staff)
        r = self.client.get(reverse("courses:gradebook", args=[self.course.id]))
        self.assertContains(r, self.hidden.title)    # next load, new column (FR-21)

    def test_makeup_released_test_shows_beside_main(self):
        from assessments.services import set_makeup_students
        makeup = make_test(self.course, n_obj=1, is_makeup=True, title="Makeup Quiz")
        add_mcq(makeup)
        set_makeup_students(makeup, actor=self.staff, user_ids=[self.bode.id])
        open_test(makeup)
        a = start_attempt(makeup, student=self.bode)
        save_answer(a, question_id=a.drawn_questions()[0].id, choice="B")
        release_results(makeup, actor=self.staff)
        self.client.force_login(self.bode)
        r = self.client.get(reverse("courses:gradebook", args=[self.course.id]))
        self.assertContains(r, makeup.title)
        self.assertContains(r, "Makeup")
        self.client.force_login(self.staff)
        r = self.client.get(reverse("courses:gradebook", args=[self.course.id]))
        self.assertContains(r, makeup.title)  # recorded beside the main test

    def test_outsider_is_turned_away(self):
        outsider = make_user(username="MOUAU/PSB/26/099999", reg_no="MOUAU/PSB/26/099999")
        self.client.force_login(outsider)
        r = self.client.get(reverse("courses:gradebook", args=[self.course.id]))
        self.assertEqual(r.status_code, 302)
