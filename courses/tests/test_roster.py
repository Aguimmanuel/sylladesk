import io

from django.test import TestCase

from accounts.tests.helpers import make_user
from courses.models import RosterEntry
from courses.services import import_roster
from courses.tests.helpers import make_course

REG = "MOUAU/PSB/26/012345"

CSV1 = (
    "registration_number,full_name\n"
    f"{REG},Ada Obi\n"
    "mouau psb 26 012346,Tunde Bello\n"  # messy spacing -> normalized
    "MOUAU/PSB/26/012347,\n"
) + "\n"  # no name (allowed)


class RosterImportTests(TestCase):
    def setUp(self):
        self.course = make_course()

    def _run(self, text):
        return import_roster(self.course, io.StringIO(text), actor=None)

    def test_first_import_counts(self):
        r = self._run(CSV1)
        self.assertEqual(r.total_rows, 3)
        self.assertEqual(r.added, 3)
        self.assertEqual(RosterEntry.objects.filter(course=self.course).count(), 3)
        self.assertEqual(
            RosterEntry.objects.get(reg_no="MOUAUPSB26012346").full_name, "Tunde Bello"
        )  # "psb 2023 002" normalized

    def test_identical_reimport_changes_nothing(self):
        self._run(CSV1)
        r = self._run(CSV1)
        self.assertEqual(
            (r.added, r.renamed, r.reactivated, r.deactivated), (0, 0, 0, 0)
        )

    def test_absent_row_deactivated_not_deleted(self):
        self._run(CSV1)
        r = self._run(f"registration_number,full_name\n{REG},Ada Obi\n")
        self.assertEqual(r.deactivated, 2)
        e = RosterEntry.objects.get(reg_no="MOUAUPSB26012346")  # from the spaced row
        self.assertFalse(e.is_active)
        self.assertTrue(RosterEntry.objects.filter(reg_no="MOUAUPSB26012346").exists())

    def test_readdition_reactivates(self):
        self._run(CSV1)
        self._run(f"registration_number,full_name\n{REG},Ada Obi\n")
        r = self._run(CSV1)
        self.assertEqual(r.reactivated, 2)

    def test_claimed_names_never_renamed(self):
        self._run(CSV1)
        e = RosterEntry.objects.get(reg_no=REG)
        from django.utils import timezone

        s = make_user(username=REG, reg_no=REG)
        e.claimed_by = s
        e.claimed_at = timezone.now()
        e.save()
        self._run(f"registration_number,full_name\n{REG},Wrong Name\n")
        e.refresh_from_db()
        self.assertEqual(e.full_name, "Ada Obi")

    def test_import_audited(self):
        from core.models import AuditLog

        self._run(CSV1)
        self.assertTrue(AuditLog.objects.filter(action="roster.import").exists())
