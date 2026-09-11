import io

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from core.models import File
from core.storage import get_storage
from core.templatetags.lms_extras import size_label, wat


class HealthzTests(TestCase):
    def test_healthy(self):
        r = self.client.get("/healthz")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["database"], True)


class StorageTests(TestCase):
    def test_db_storage_roundtrip(self):
        storage = get_storage()  # default FILES_BACKEND=db in tests
        up = SimpleUploadedFile("leaf.pdf", b"fake pdf bytes", content_type="application/pdf")
        f = storage.save(up, course_id=None, kind="test", uploaded_by=None)
        self.assertIsInstance(f, File)
        self.assertEqual(f.size_bytes, 14)  # len(b"fake pdf bytes")
        self.assertEqual(len(f.sha256), 64)
        with storage.open(f) as fh:
            self.assertEqual(fh.read(), b"fake pdf bytes")
        storage.delete(f)
        self.assertFalse(File.objects.filter(pk=f.pk).exists())


class TemplateFiltersTests(TestCase):
    def test_size_labels(self):
        self.assertEqual(size_label(0), "0 B")
        self.assertEqual(size_label(1280), "1.3 KB")
        self.assertEqual(size_label(2_750_000), "2.6 MB")

    def test_wat_label(self):
        import datetime
        from django.utils import timezone
        dt = timezone.make_aware(datetime.datetime(2026, 9, 10, 13, 5))
        self.assertTrue(wat(dt).endswith("WAT"))
