from django.test import TestCase
from django.utils import timezone

from accounts.tests.helpers import make_user
from courses.tests.helpers import make_course

from core.models import AuditLog

from ..models import Submission
from ..services import (create_assignment, delete_assignment, grade_submission,
                        roster_status, submit_assignment, update_assignment)
from .helpers import (DOCX_BYTES, PDF_BYTES, enroll, make_assignment,
                      make_student, upload)


class CreateTests(TestCase):
    def test_create_with_future_deadline(self):
        c = make_course()
        a = create_assignment(c, actor=c.lecturer, title="Report",
                              instructions="Do it", max_score=25,
                              due_at=timezone.now() + timezone.timedelta(days=2),
                              allowed_ext="pdf,doc,docx")
        self.assertEqual(a.max_score, 25)
        self.assertTrue(AuditLog.objects.filter(action="assignment.create").exists())

    def test_past_deadline_rejected(self):
        c = make_course()
        with self.assertRaises(ValueError):
            create_assignment(c, actor=c.lecturer, title="Report",
                              instructions="", max_score=10,
                              due_at=timezone.now() - timezone.timedelta(hours=1),
                              allowed_ext="pdf")


class EditTests(TestCase):
    def test_full_edit_until_deadline(self):
        a = make_assignment()
        update_assignment(a, actor=a.created_by,
                          data={"title": "Renamed", "max_score": 40})
        a.refresh_from_db()
        self.assertEqual((a.title, a.max_score), ("Renamed", 40))

    def test_full_edit_allowed_after_submissions(self):
        """The lecturer owns the assignment; submissions do not lock it."""
        a = make_assignment()
        s = make_student()
        enroll(a.course, s)
        submit_assignment(a, student=s, uploaded=upload())
        update_assignment(a, actor=a.created_by,
                          data={"title": "Renamed", "instructions": "Also cite sources."})
        a.refresh_from_db()
        self.assertEqual(a.title, "Renamed")
        self.assertIn("cite sources", a.instructions)

    def test_edit_allowed_after_deadline(self):
        a = make_assignment(due=timezone.now() - timezone.timedelta(hours=1))
        update_assignment(a, actor=a.created_by, data={"max_score": 40})
        a.refresh_from_db()
        self.assertEqual(a.max_score, 40)

    def test_soft_delete_hides_assignment_keeps_rows(self):
        a = make_assignment()
        s = make_student()
        enroll(a.course, s)
        sub = submit_assignment(a, student=s, uploaded=upload())
        delete_assignment(a, actor=a.created_by)
        a.refresh_from_db()
        self.assertFalse(a.is_active)
        self.assertTrue(Submission.objects.filter(pk=sub.pk).exists())  # records kept
        self.assertTrue(AuditLog.objects.filter(action="assignment.delete").exists())


class SubmitTests(TestCase):
    def test_submit_receipt_and_resubmit_history(self):
        a = make_assignment()
        s = make_student()
        enroll(a.course, s)
        sub1 = submit_assignment(a, student=s, uploaded=upload(),
                                 note="first try")
        self.assertEqual(sub1.attempt_no, 1)
        self.assertFalse(sub1.is_late)
        self.assertEqual(sub1.file.sha256[:10], sub1.file.sha256[:10])  # stored on the file
        sub2 = submit_assignment(a, student=s, uploaded=upload(name="v2.pdf"))
        self.assertEqual(sub2.attempt_no, 2)
        self.assertEqual(Submission.objects.filter(assignment=a, student=s).count(), 2)
        self.assertTrue(AuditLog.objects.filter(action="submission.create").exists())

    def test_late_within_grace_accepted_and_flagged(self):
        a = make_assignment(due=timezone.now() - timezone.timedelta(seconds=30))
        s = make_student()
        enroll(a.course, s)
        sub = submit_assignment(a, student=s, uploaded=upload())
        self.assertTrue(sub.is_late)  # past due counts as late, even inside grace

    def test_after_grace_refused(self):
        a = make_assignment(due=timezone.now() - timezone.timedelta(minutes=5))
        s = make_student()
        enroll(a.course, s)
        with self.assertRaises(ValueError):
            submit_assignment(a, student=s, uploaded=upload())

    def test_not_enrolled_refused(self):
        a = make_assignment()
        with self.assertRaises(ValueError):
            submit_assignment(a, student=make_student(), uploaded=upload())

    def test_wrong_extension_refused(self):
        a = make_assignment()
        s = make_student()
        enroll(a.course, s)
        with self.assertRaises(ValueError):
            submit_assignment(a, student=s, uploaded=upload(name="notes.txt"))

    def test_renamed_file_refused(self):
        a = make_assignment()
        s = make_student()
        enroll(a.course, s)
        with self.assertRaises(ValueError):
            submit_assignment(a, student=s, uploaded=upload(name="fake.pdf", content=DOCX_BYTES))

    def test_oversized_file_refused(self):
        a = make_assignment()
        s = make_student()
        enroll(a.course, s)
        big = PDF_BYTES + b"\x00" * (16 * 1024 * 1024)
        with self.assertRaises(ValueError):
            submit_assignment(a, student=s, uploaded=upload(content=big))


class GradeTests(TestCase):
    def test_grade_and_regrade_audited(self):
        a = make_assignment()
        s = make_student()
        enroll(a.course, s)
        sub = submit_assignment(a, student=s, uploaded=upload())
        grade_submission(sub, actor=a.created_by, score=22, note="good figures")
        sub.refresh_from_db()
        self.assertEqual(sub.score, 22)
        grade_submission(sub, actor=a.created_by, score=25)
        actions = list(AuditLog.objects.filter(action="submission.grade")
                       .values_list("detail", flat=True))
        self.assertIn("22", str(actions[-1]))  # old -> new recorded

    def test_over_max_rejected(self):
        a = make_assignment()
        s = make_student()
        enroll(a.course, s)
        sub = submit_assignment(a, student=s, uploaded=upload())
        with self.assertRaises(ValueError):
            grade_submission(sub, actor=a.created_by, score=31)


class RosterStatusTests(TestCase):
    def test_submitted_late_missing(self):
        a = make_assignment()
        on_time = make_student(reg="MOUAU/PSB/26/060001")
        late = make_student(reg="MOUAU/PSB/26/060002")
        missing = make_student(reg="MOUAU/PSB/26/060003")
        for st in (on_time, late, missing):
            enroll(a.course, st)
        submit_assignment(a, student=on_time, uploaded=upload())
        a.due_at = timezone.now() - timezone.timedelta(seconds=30)
        a.save()
        submit_assignment(a, student=late, uploaded=upload())
        rows = {r["student"].id: r for r in roster_status(a)}
        self.assertEqual(rows[on_time.id]["state"], "submitted")
        self.assertEqual(rows[late.id]["state"], "late")
        self.assertEqual(rows[missing.id]["state"], "missing")

    def test_resubmit_after_grading_refused(self):
        a = make_assignment()
        s = make_student()
        enroll(a.course, s)
        sub = submit_assignment(a, student=s, uploaded=upload())
        grade_submission(sub, actor=a.created_by, score=18)
        with self.assertRaises(ValueError):
            submit_assignment(a, student=s, uploaded=upload(name="v2.pdf"))
        self.assertEqual(Submission.objects.filter(assignment=a, student=s).count(), 1)
