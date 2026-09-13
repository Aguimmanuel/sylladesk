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


class EnsureOwnerTests(TestCase):
    def test_creates_owner_from_env_and_is_idempotent(self):
        import os
        from unittest.mock import patch

        from django.contrib.auth import get_user_model
        from django.core.management import call_command

        User = get_user_model()
        env = {
            "OWNER_USERNAME": "owner@sylladesk.app",
            "OWNER_EMAIL": "owner@sylladesk.app",
            "OWNER_PASSWORD": "very-strong-owner-pw-9",
        }
        with patch.dict(os.environ, env):
            call_command("ensure_owner", verbosity=0)
            self.assertTrue(
                User.objects.filter(username="owner@sylladesk.app").exists()
            )
            call_command("ensure_owner", verbosity=0)  # second run: unchanged, no error
        owner = User.objects.get(username="owner@sylladesk.app")
        self.assertTrue(owner.is_superuser)
        self.assertEqual(owner.global_role, "admin")

    def test_refuses_without_env(self):
        import os
        from unittest.mock import patch

        from django.core.management import call_command

        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(Exception):
                call_command("ensure_owner", verbosity=0)