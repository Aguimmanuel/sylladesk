import io

from django.contrib.auth import get_user_model
from django.test import TestCase

from accounts.services import import_staff_csv

User = get_user_model()

CSV = "\n".join([
    "full_name,email,role",
    "Ada Obi,ada@psb.lms,lecturer",
    "Tunde Bello,tunde@psb.lms,lecturer",
    "Dup Ada,ada@psb.lms,lecturer",          # duplicate in-file
    "Existing,existing@psb.lms,lecturer",     # already exists (seeded below)
    "No Email,,lecturer",                      # invalid email
    "Weird Role,weird@psb.lms,professor",     # unknown role
]) + "\n"


class StaffImportTests(TestCase):
    def setUp(self):
        User.objects.create(username="existing@psb.lms", email="existing@psb.lms",
                            full_name="Existing")

    def test_report_counts_and_skip_reasons(self):
        report = import_staff_csv(io.StringIO(CSV), actor=None)
        self.assertEqual(report.total_rows, 6)
        self.assertEqual(report.created, 2)
        reasons = {reason: None for _, _, reason in report.skipped}
        self.assertEqual(len(report.skipped), 4)
        self.assertIn("duplicate row in this file", reasons)
        self.assertIn("account already exists", reasons)
        self.assertIn("invalid email", reasons)
        self.assertIn("unknown role 'professor'", reasons)

    def test_created_accounts_are_temp_credential_state(self):
        import_staff_csv(io.StringIO(CSV), actor=None)
        ada = User.objects.get(username="ada@psb.lms")
        self.assertEqual(ada.global_role, User.GlobalRole.LECTURER)
        self.assertTrue(ada.must_reset_password)
        self.assertFalse(ada.has_usable_password())

    def test_idempotent_rerun_creates_nothing_new(self):
        import_staff_csv(io.StringIO(CSV), actor=None)
        before = User.objects.count()
        report = import_staff_csv(io.StringIO(CSV), actor=None)
        self.assertEqual(report.created, 0)
        self.assertEqual(User.objects.count(), before)

    def test_import_is_audited(self):
        from core.models import AuditLog
        import_staff_csv(io.StringIO(CSV), actor=None)
        self.assertTrue(AuditLog.objects.filter(action="staff.import").exists())
