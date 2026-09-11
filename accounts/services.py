"""Accounts business logic, plain functions (convention #1: fat services, thin views)."""
import csv
import io
import re
from dataclasses import dataclass, field

from django.contrib.auth import get_user_model
from django.db import transaction

from core.auditing import audit

User = get_user_model()
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_ROLES = {"lecturer": User.GlobalRole.LECTURER, "admin": User.GlobalRole.ADMIN}


@dataclass
class ImportReport:
    total_rows: int = 0
    created: int = 0
    skipped: list = field(default_factory=list)  # [(row_no, email, reason)]

    def summary(self) -> str:
        lines = [f"{self.created}/{self.total_rows} staff accounts imported."]
        lines += [f"  skipped row {r}: {email} — {reason}" for r, email, reason in self.skipped]
        return "\n".join(lines)


@transaction.atomic
def import_staff_csv(fileobj, *, actor=None) -> ImportReport:
    """FR-03: CSV with columns full_name,email[,role]. Per-row validation,
    skip-with-reason report, idempotent re-runs (existing emails skipped).
    Created users get an unusable password + must_reset_password=True (FR-01)."""
    report = ImportReport()
    data = fileobj.read()
    if isinstance(data, bytes):
        data = data.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(data))
    seen_emails = set()

    for row_no, row in enumerate(reader, start=2):
        report.total_rows += 1
        name = (row.get("full_name") or "").strip()
        email = (row.get("email") or "").strip().lower()
        role = (row.get("role") or "lecturer").strip().lower()

        if not name:
            report.skipped.append((row_no, email, "missing full_name"))
            continue
        if not _EMAIL_RE.match(email):
            report.skipped.append((row_no, email, "invalid email"))
            continue
        if role not in _ROLES:
            report.skipped.append((row_no, email, f"unknown role '{role}'"))
            continue
        if email in seen_emails:
            report.skipped.append((row_no, email, "duplicate row in this file"))
            continue
        if User.objects.filter(username=email).exists() or User.objects.filter(email=email).exists():
            report.skipped.append((row_no, email, "account already exists"))
            continue

        User.objects.create(
            username=email,
            email=email,
            full_name=name,
            global_role=_ROLES[role],
            must_reset_password=True,
        )
        User.objects.filter(username=email).update(is_staff=False)  # no-op; explicit for clarity
        u = User.objects.get(username=email)
        u.set_unusable_password()
        u.save(update_fields=["password"])
        seen_emails.add(email)
        report.created += 1

    audit(
        actor=actor,
        action="staff.import",
        detail={"created": report.created, "skipped": len(report.skipped), "total": report.total_rows},
    )
    return report
