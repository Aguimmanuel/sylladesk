from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from accounts.tests.helpers import make_user
from courses.models import Enrollment
from courses.tests.helpers import make_course
from materials.models import Material
from materials.services import create_material

PDF = b"%PDF-1.4 fake pdf content"


class MaterialUploadTests(TestCase):
    def setUp(self):
        self.course = make_course()
        self.staff = self.course.lecturer
        self.client.force_login(self.staff)

    def _post(self, name="lec3.pdf", content=PDF, ctype="application/pdf", **over):
        data = {"title": "Lecture 3", "week_no": 3, "material_file":
                SimpleUploadedFile(name, content, content_type=ctype)}
        data.update(over)
        return self.client.post(reverse("materials:upload", args=[self.course.id]), data)

    def test_upload_pdf_ok(self):
        self._post()
        self.assertEqual(Material.objects.count(), 1)
        m = Material.objects.first()
        self.assertEqual(m.file.size_bytes, len(PDF))
        self.assertTrue(m.file.storage_key.startswith(f"{self.course.id}/material/"))

    def test_bad_extension_rejected(self):
        self._post(name="notes.txt", content=b"hello")
        self.assertEqual(Material.objects.count(), 0)

    def test_renamed_exe_rejected_by_magic(self):
        self._post(name="trojan.pdf", content=b"MZ\x90\x00 not a pdf")
        self.assertEqual(Material.objects.count(), 0)

    def test_extension_magic_mismatch_rejected(self):
        self._post(name="real.docx", content=PDF)  # PDF bytes with .docx name
        self.assertEqual(Material.objects.count(), 0)

    def test_oversize_rejected(self):
        from django.conf import settings
        big = PDF + b"\0" * (settings.MATERIAL_MAX_MB * 1024 * 1024)
        self._post(content=big)
        self.assertEqual(Material.objects.count(), 0)

    def test_student_cannot_upload(self):
        s = make_user(username="stu1")
        Enrollment.objects.create(course=self.course, user=s)
        self.client.force_login(s)
        self._post()
        self.assertEqual(Material.objects.count(), 0)


class MaterialDownloadTests(TestCase):
    def setUp(self):
        self.course = make_course()
        self.client.force_login(self.course.lecturer)
        self.client.post(reverse("materials:upload", args=[self.course.id]),
                         {"title": "L1", "week_no": 1,
                          "material_file": SimpleUploadedFile("l1.pdf", PDF)})
        self.material = Material.objects.first()
        self.student = make_user(username="stu1")
        Enrollment.objects.create(course=self.course, user=self.student)

    def test_enrolled_student_downloads_and_counter_increments(self):
        self.client.force_login(self.student)
        before = self.material.download_count
        r = self.client.get(reverse("materials:download", args=[self.course.id, self.material.id]))
        self.assertEqual(r.status_code, 200)
        self.material.refresh_from_db()
        self.assertEqual(self.material.download_count, before + 1)

    def test_outsider_gets_404(self):
        outsider = make_user(username="mallory")
        self.client.force_login(outsider)
        r = self.client.get(reverse("materials:download", args=[self.course.id, self.material.id]))
        self.assertEqual(r.status_code, 404)

    def test_soft_delete_hides_from_students(self):
        self.client.force_login(self.course.lecturer)
        self.client.post(reverse("materials:delete", args=[self.course.id, self.material.id]))
        self.client.force_login(self.student)
        r = self.client.get(reverse("materials:download", args=[self.course.id, self.material.id]))
        self.assertEqual(r.status_code, 404)

    def test_upload_form_targets_upload_endpoint(self):
        """The upload form must post to the upload endpoint, not the course page."""
        self.client.force_login(self.course.lecturer)  # self-contained: works in either test class
        r = self.client.get(reverse("courses:detail", args=[self.course.id]))
        self.assertContains(
            r, 'action="' + reverse("materials:upload", args=[self.course.id]) + '"')

    def test_view_inline_and_download_attachment(self):
        from django.test import Client
        from accounts.tests.helpers import make_user
        from courses.models import Enrollment
        m = create_material(course=self.course, title="Ch 1", week_no=1,
                            uploaded=SimpleUploadedFile("ch1.pdf", PDF,
                                                        content_type="application/pdf"),
                            actor=self.course.lecturer).material
        student = make_user(username="MOUAU/PSB/26/091001", reg_no="MOUAU/PSB/26/091001")
        Enrollment.objects.create(course=self.course, user=student, role_in_course="student")
        outsider = make_user(username="MOUAU/PSB/26/091002", reg_no="MOUAU/PSB/26/091002")
        c = Client()
        c.force_login(student)
        r = c.get(reverse("materials:view", args=[self.course.id, m.id]))
        self.assertEqual(r.status_code, 200)
        self.assertIn("inline", r["Content-Disposition"])
        r = c.get(reverse("materials:download", args=[self.course.id, m.id]))
        self.assertIn("attachment", r["Content-Disposition"])
        c.force_login(outsider)
        self.assertEqual(c.get(reverse("materials:view", args=[self.course.id, m.id])).status_code, 404)
