"""Roster import (FR-06) — idempotent, claimed-aware, audited."""
import csv
import io
from dataclasses import dataclass, field

from django.utils import timezone

from core.auditing import audit
from core.utils import normalize_reg_no

from .models import RosterEntry


@dataclass
class RosterReport:
    total_rows: int = 0
    added: int = 0
    renamed: int = 0        # name set/changed on UNCLAIMED entries only
    reactivated: int = 0
    deactivated: int = 0
    skipped: list = field(default_factory=list)  # [(row_no, reg, reason)]

    def summary(self) -> str:
        return (f"{self.total_rows} rows: {self.added} added, {self.renamed} renamed, "
                f"{self.reactivated} reactivated, {self.deactivated} deactivated, "
                f"{len(self.skipped)} skipped.")


def import_roster(course, fileobj, *, actor=None) -> RosterReport:
    report = RosterReport()
    data = fileobj.read()
    if isinstance(data, bytes):
        data = data.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(data))
    existing = {e.reg_no: e for e in RosterEntry.objects.filter(course=course)}
    seen = set()

    for row_no, row in enumerate(reader, start=2):
        report.total_rows += 1
        reg = normalize_reg_no(row.get("registration_number") or row.get("reg_no"))
        name = (row.get("full_name") or "").strip()
        if not reg:
            report.skipped.append((row_no, reg or "?", "missing registration_number"))
            continue
        if reg in seen:
            report.skipped.append((row_no, reg, "duplicate row in this file"))
            continue
        seen.add(reg)
        entry = existing.get(reg)
        if entry is None:
            RosterEntry.objects.create(course=course, reg_no=reg, full_name=name)
            report.added += 1
            continue
        changed = []
        if name and not entry.claimed_by and entry.full_name != name:
            entry.full_name = name
            changed.append("renamed")
        if not entry.is_active:
            entry.is_active = True
            changed.append("reactivated")
        if changed:
            entry.save()
            if "renamed" in changed:
                report.renamed += 1
            if "reactivated" in changed:
                report.reactivated += 1

    # absent-from-file → deactivate (never delete; records preserved, FR-06)
    for reg, entry in existing.items():
        if reg not in seen and entry.is_active:
            entry.is_active = False
            entry.save(update_fields=["is_active", "updated_at"])
            report.deactivated += 1

    audit(
        actor=actor, action="roster.import", obj=course,
        detail={"added": report.added, "renamed": report.renamed,
                "reactivated": report.reactivated, "deactivated": report.deactivated,
                "skipped": len(report.skipped), "rows": report.total_rows},
    )
    return report


def claim_roster_entries(user):
    """On signup (FR-33): claim every unclaimed roster entry for user.reg_no and
    enroll the user in each course. Must run inside a transaction; caller did the
    matching/validation already. Returns the list of courses joined."""
    from .models import Enrollment

    entries = RosterEntry.objects.select_for_update().filter(
        reg_no=user.reg_no, claimed_by__isnull=True, is_active=True
    ).select_related("course")
    courses = []
    now = timezone.now()
    for entry in entries:
        entry.claimed_by = user
        entry.claimed_at = now
        entry.save(update_fields=["claimed_by", "claimed_at", "updated_at"])
        Enrollment.objects.get_or_create(
            course=entry.course, user=user,
            defaults={"role_in_course": Enrollment.Role.STUDENT},
        )
        courses.append(entry.course)
    return courses
