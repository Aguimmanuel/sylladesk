"""Assignment and submission rules. Server clock only; one grace window."""
import io

from django.utils import timezone

from core.auditing import audit
from core.models import File
from core.storage import get_storage
from core.utils import normalize_reg_no
from courses.access import user_role_in_course

from .models import GRACE_SECONDS, Assignment, Submission

# extension -> allowed magic-byte signatures (submissions are documents only)
_DOC_FAMILIES = {
    "pdf": (b"%PDF-",),
    "doc": (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1",),
    "docx": (b"PK\x03\x04",),
}
MAX_MB = 15


def deadline_with_grace(assignment):
    return assignment.due_at + timezone.timedelta(seconds=GRACE_SECONDS)


def _validate_file(uploaded, assignment):
    ext = uploaded.name.rsplit(".", 1)[-1].lower() if "." in uploaded.name else ""
    allowed = [e.strip().lower() for e in assignment.allowed_ext.split(",") if e.strip()]
    if ext not in allowed:
        return False, f"Allowed file types: {', '.join(allowed)}."
    if uploaded.size > MAX_MB * 1024 * 1024:
        return False, f"File is too large. Maximum is {MAX_MB} MB."
    signatures = _DOC_FAMILIES.get(ext)
    head = uploaded.read(8)
    uploaded.seek(0)
    if signatures and not any(head.startswith(s) for s in signatures):
        return False, "That file's contents do not match its extension."
    return True, ""


def create_assignment(course, *, actor, title, instructions, max_score, due_at, allowed_ext):
    if due_at <= timezone.now():
        raise ValueError("The due date must be in the future.")
    a = Assignment.objects.create(
        course=course, title=title.strip(), instructions=instructions,
        max_score=max_score, due_at=due_at,
        allowed_ext=",".join(e.strip().lower() for e in allowed_ext.split(",") if e.strip()),
        created_by=actor,
    )
    audit(actor=actor, action="assignment.create", obj=a)
    return a


def update_assignment(a, *, actor, data):
    """Full edits until the deadline; once anything is submitted, only the
    instructions may change (clarifications), and never past the deadline."""
    now = timezone.now()
    has_submissions = a.submissions.exists()
    if now > a.due_at:
        raise ValueError("The deadline has passed; the assignment is locked.")
    if has_submissions:
        allowed = {"instructions"}
        unknown = set(data) - allowed
        if unknown:
            raise ValueError(
                "A student has already submitted; only the instructions may be changed."
            )
    for field, value in data.items():
        setattr(a, field, value)
    a.save()
    audit(actor=actor, action="assignment.update", obj=a, detail={"fields": sorted(data)})
    return a


def submit_assignment(a, *, student, uploaded, note=""):
    """One file, one attempt. Retry-safe under double-taps: the attempt number
    is allocated inside a row lock, and the unique constraint backstops races."""
    from django.db import transaction

    now = timezone.now()
    if now > deadline_with_grace(a):
        raise ValueError("The deadline has passed; submissions are closed.")
    if a.submissions.filter(student=student, graded_at__isnull=False).exists():
        raise ValueError("This work has already been marked; resubmission is closed.")
    if user_role_in_course(student, a.course) != "student":
        raise ValueError("Only enrolled students can submit.")
    ok, error = _validate_file(uploaded, a)
    if not ok:
        raise ValueError(error)

    with transaction.atomic():
        last = (
            Submission.objects.select_for_update()
            .filter(assignment=a, student=student)
            .order_by("-attempt_no")
            .first()
        )
        attempt_no = (last.attempt_no + 1) if last else 1
        f = get_storage().save(uploaded, course_id=a.course_id, kind="submission", uploaded_by=student)
        s = Submission.objects.create(
            assignment=a, student=student, attempt_no=attempt_no,
            file=f, note=note[:1000], is_late=now > a.due_at,
        )
    audit(actor=student, action="submission.create", obj=s,
          detail={"attempt": attempt_no, "sha256": f.sha256, "late": s.is_late})
    return s


def grade_submission(s, *, actor, score, note=""):
    if score is not None and score > s.assignment.max_score:
        raise ValueError(f"Score cannot exceed the maximum of {s.assignment.max_score}.")
    old = s.score
    s.score = score
    s.score_note = note[:500]
    s.graded_at = timezone.now()
    s.graded_by = actor
    s.save(update_fields=["score", "score_note", "graded_at", "graded_by"])
    audit(actor=actor, action="submission.grade", obj=s, detail={"old": old, "new": score})
    return s


def roster_status(a):
    """Who submitted, who is late, who is missing — active students only."""
    enrolled = a.course.enrollments.filter(role_in_course="student", is_active=True)\
        .select_related("user").order_by("user__full_name")
    by_student = {}
    for s in a.submissions.select_related("student", "file").order_by("attempt_no"):
        by_student.setdefault(s.student_id, []).append(s)
    rows = []
    for e in enrolled:
        attempts = by_student.get(e.user_id, [])
        latest = attempts[-1] if attempts else None
        rows.append({
            "student": e.user,
            "attempts": attempts,
            "latest": latest,
            "state": "missing" if not latest else ("late" if latest.is_late else "submitted"),
        })
    return rows
