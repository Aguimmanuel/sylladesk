from django.db import IntegrityError
from django.test import TestCase
from django.urls import reverse

from accounts.tests.helpers import make_user
from courses.models import Course
from courses.tests.helpers import make_course, make_lecturer


class CourseCreateTests(TestCase):
    def test_lecturer_creates_course(self):
        lecturer = make_lecturer()
        self.client.force_login(lecturer)
        r = self.client.post(reverse("courses:create"), {
            "code": "PSB 413", "title": "Physiology",
            "session": "2025/2026", "semester": "first",
        })
        self.assertTrue(Course.objects.filter(code="PSB 413").exists())

    def test_duplicate_code_session_blocked(self):
        c = make_course()
        self.client.force_login(c.lecturer)
        r = self.client.post(reverse("courses:create"), {
            "code": c.code, "title": "Dup", "session": c.session, "semester": "second",
        })
        self.assertContains(r, "already exists")

    def test_student_cannot_create(self):
        s = make_user(username="stu1")
        self.client.force_login(s)
        r = self.client.post(reverse("courses:create"), {
            "code": "X 1", "title": "T", "session": "2025/2026", "semester": "first",
        })
        self.assertEqual(Course.objects.count(), 0)


class CourseVisibilityTests(TestCase):
    def test_student_sees_only_enrolled(self):
        from courses.models import Enrollment
        c1, c2 = make_course(code="A 1"), make_course(code="B 2")
        s = make_user(username="stu1")
        Enrollment.objects.create(course=c1, user=s)
        self.client.force_login(s)
        r = self.client.get(reverse("courses:list"))
        self.assertContains(r, "A 1")
        self.assertNotContains(r, "B 2")

    def test_detail_denied_to_unenrolled_student(self):
        c = make_course()
        s = make_user(username="stu1")
        self.client.force_login(s)
        r = self.client.get(reverse("courses:detail", args=[c.id]), follow=True)
        self.assertContains(r, "not enrolled")

    def test_admin_role_passes_everywhere(self):
        c = make_course()
        a = make_user(username="owner@psb.lms", global_role="admin")
        self.client.force_login(a)
        r = self.client.get(reverse("courses:detail", args=[c.id]))
        self.assertEqual(r.status_code, 200)

    def test_duplicate_code_different_case_blocked(self):
        """Course codes are normalized before the uniqueness check."""
        make_course()  # PSB 413 / 2025/2026
        self.client.force_login(make_lecturer())
        r = self.client.post(reverse("courses:create"), {
            "code": "psb 413", "title": "Copycat",
            "session": "2025/2026", "semester": "first"})
        self.assertContains(r, "already exists")
        self.assertEqual(Course.objects.filter(code="PSB 413").count(), 1)

    def test_co_lecturer_sees_course_in_list(self):
        """A co-lecturer (lecturer-role enrollment) sees the course in My courses."""
        from courses.models import Enrollment
        c = make_course()
        co = make_user(username="colect@psb.lms", global_role="lecturer")
        Enrollment.objects.create(course=c, user=co, role_in_course=Enrollment.Role.LECTURER)
        self.client.force_login(co)
        r = self.client.get(reverse("courses:list"))
        self.assertContains(r, c.code)

    def test_admin_sees_all_courses_in_list(self):
        from courses.models import Enrollment
        c = make_course()
        owner = make_user(username="platadmin@psb.lms", global_role="admin")
        owner.is_staff = True; owner.save()
        self.client.force_login(owner)
        r = self.client.get(reverse("courses:list"))
        self.assertContains(r, c.code)
