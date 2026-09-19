import hashlib

from django.test import TestCase
from django.urls import reverse

from accounts.tests.helpers import make_user
from assessments.models import Test
from assessments.tests.helpers import add_mcq, make_test
from assignments.models import Assignment
from assignments.tests.helpers import make_assignment
from core.models import File, FileBlob
from courses.tests.helpers import make_course
from materials.models import Material

from .helpers import make_lecturer


def make_material(course, *, title="Week 1 Slides", deleted=False):
    data = b"%PDF-1.4\ntrash-test\n%%EOF\n"
    key = f"trash-{title.replace(' ', '-')}"
    FileBlob.objects.create(key=key, data=data)
    f = File.objects.create(
        storage_key=key, original_name="slides.pdf", mime="application/pdf",
        size_bytes=len(data), sha256=hashlib.sha256(data).hexdigest(),
    )
    m = Material.objects.create(
        course=course, title=title, week_no=1, file=f, uploaded_by=course.lecturer,
    )
    if deleted:
        m.is_deleted = True
        m.save(update_fields=["is_deleted"])
    return m


class TrashTests(TestCase):
    def setUp(self):
        _lecturer = make_lecturer()
        self.course = make_course(lecturer=_lecturer)
        self.staff = self.course.lecturer

    def test_trash_page_lists_all_three_kinds_and_students_never_see_it(self):
        make_material(self.course, deleted=True)
        t = make_test(self.course, n_obj=1)
        t.is_active = False
        t.save()
        a = make_assignment(self.course)
        a.is_active = False
        a.save()
        self.client.force_login(self.staff)
        r = self.client.get(reverse("courses:trash", args=[self.course.id]))
        self.assertContains(r, "Week 1 Slides")
        self.assertContains(r, t.title)
        self.assertContains(r, a.title)
        student = make_user(username="MOUAU/PSB/26/080001", reg_no="MOUAU/PSB/26/080001")
        self.client.force_login(student)
        r = self.client.get(reverse("courses:trash", args=[self.course.id]))
        self.assertEqual(r.status_code, 302)

    def test_restore_brings_each_kind_back(self):
        m = make_material(self.course, deleted=True)
        t = make_test(self.course, n_obj=1)
        t.is_active = False
        t.save()
        a = make_assignment(self.course)
        a.is_active = False
        a.save()
        self.client.force_login(self.staff)
        for kind, obj in (("material", m), ("test", t), ("assignment", a)):
            r = self.client.post(reverse("courses:trash_restore",
                                         args=[self.course.id, kind, obj.id]))
            self.assertEqual(r.status_code, 302)
        self.assertEqual(Material.objects.filter(course=self.course, is_deleted=False).count(), 1)
        self.assertTrue(Test.objects.get(pk=t.pk).is_active)
        self.assertTrue(Assignment.objects.get(pk=a.pk).is_active)

    def test_delete_for_good_destroys_material_and_file_bytes(self):
        m = make_material(self.course, deleted=True)
        key = m.file.storage_key
        self.client.force_login(self.staff)
        r = self.client.post(reverse("courses:trash_delete",
                                     args=[self.course.id, "material", m.id]))
        self.assertEqual(r.status_code, 302)
        self.assertFalse(Material.objects.filter(pk=m.pk).exists())
        self.assertFalse(File.objects.filter(storage_key=key).exists())
        self.assertFalse(FileBlob.objects.filter(key=key).exists())

    def test_delete_for_good_refused_when_student_records_exist(self):
        from assessments.tests.helpers import open_test, enroll, make_student_enrolled
        from assessments.services import start_attempt
        t = make_test(self.course, n_obj=1)
        add_mcq(t)
        open_test(t)
        s = make_student_enrolled()
        enroll(self.course, s)
        start_attempt(t, student=s)
        t.is_active = False
        t.save()
        a = make_assignment(self.course)
        a.is_active = False
        a.save()
        # a real submission: immutable student records are the whole point
        data = b"%PDF-1.4\nsubmission\n%%EOF\n"
        key = "sub-trash-test"
        FileBlob.objects.create(key=key, data=data)
        f = File.objects.create(
            storage_key=key, original_name="sub.pdf", mime="application/pdf",
            size_bytes=len(data), sha256=hashlib.sha256(data).hexdigest(),
        )
        from assignments.models import Submission
        Submission.objects.create(assignment=a, student=self.staff, attempt_no=1, file=f)
        self.client.force_login(self.staff)
        r = self.client.post(reverse("courses:trash_delete",
                                     args=[self.course.id, "test", t.id]), follow=True)
        self.assertContains(r, "cannot be deleted for good")
        self.assertTrue(Test.objects.filter(pk=t.pk).exists())
        r = self.client.post(reverse("courses:trash_delete",
                                     args=[self.course.id, "assignment", a.id]), follow=True)
        self.assertContains(r, "cannot be deleted for good")
        self.assertTrue(Assignment.objects.filter(pk=a.pk).exists())

    def test_delete_for_good_test_without_attempts(self):
        t = make_test(self.course, n_obj=1)
        add_mcq(t)
        t.is_active = False
        t.save()
        self.client.force_login(self.staff)
        r = self.client.post(reverse("courses:trash_delete",
                                     args=[self.course.id, "test", t.id]))
        self.assertEqual(r.status_code, 302)
        self.assertFalse(Test.objects.filter(pk=t.pk).exists())

    def test_course_page_shows_trash_link_with_count(self):
        make_material(self.course, deleted=True)
        self.client.force_login(self.staff)
        r = self.client.get(reverse("courses:detail", args=[self.course.id]))
        self.assertContains(r, "Trash (1)")
