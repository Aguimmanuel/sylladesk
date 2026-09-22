"""Test lifecycle rules. The server clock is the only clock.

Draft -> started (lecturer presses Start) -> closed or released. Questions
and settings lock once the test starts. Each attempt walks the sections in
order; a section's deadline is fixed when the student enters it, and sections
already left stay sealed.
"""
import secrets
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from core.auditing import audit

from .models import SECTION_OF_KIND, Answer, Attempt, Question, Test, make_join_code

GRACE_SECONDS = 10  # saves and submits in flight at a deadline still count
MIN_SECONDS, MAX_SECONDS = 5, 7200
SECTION_KEYS = ("objective", "tf", "subjective")


def _check_draw(counts):
    if sum(counts.values()) < 1:
        raise ValueError("Draw at least one question across the sections.")


def _check_seconds(seconds_by_key):
    for seconds in seconds_by_key.values():
        if not (MIN_SECONDS <= seconds <= MAX_SECONDS):
            raise ValueError("Seconds per question must be between 5 and 7200.")


def create_test(course, *, actor, title, n_objective=0, n_tf=0, n_subjective=0,
                seconds_objective=20, seconds_tf=20, seconds_subjective=60,
                points_per_question=1, is_makeup=False):
    _check_draw({"objective": n_objective, "tf": n_tf, "subjective": n_subjective})
    _check_seconds({"objective": seconds_objective, "tf": seconds_tf,
                    "subjective": seconds_subjective})
    t = Test(
        course=course, title=title.strip(), join_code=make_join_code(),
        n_objective=n_objective, n_tf=n_tf, n_subjective=n_subjective,
        seconds_objective=seconds_objective, seconds_tf=seconds_tf,
        seconds_subjective=seconds_subjective,
        points_per_question=points_per_question, is_makeup=is_makeup,
        created_by=actor,
    )
    t.save()
    audit(actor=actor, action="test.create", obj=t)
    return t


def update_settings(t, *, actor, **fields):
    """Draw sizes and pacing are editable until the test starts."""
    if t.started_at:
        raise ValueError("Settings are locked once the test has started.")
    if t.results_released_at:
        raise ValueError("Results are already out.")
    _check_draw({k: fields[k] for k in ("n_objective", "n_tf", "n_subjective")})
    _check_seconds({k: fields[k] for k in ("seconds_objective", "seconds_tf", "seconds_subjective")})
    for f, value in fields.items():
        setattr(t, f, value)
    t.save()
    audit(actor=actor, action="test.update", obj=t)
    return t


def set_makeup_students(t, *, actor, user_ids):
    """Who may take a makeup test. Only enrolled students of the course,
    locked once the test starts."""
    from courses.models import Enrollment
    if not t.is_makeup:
        raise ValueError("This test is not a makeup test.")
    if t.started_at:
        raise ValueError("Students are locked once the test has started.")
    wanted = {int(i) for i in user_ids}
    enrolled = set(
        Enrollment.objects.filter(
            course=t.course, role_in_course="student", is_active=True
        ).values_list("user_id", flat=True)
    )
    if wanted - enrolled:
        raise ValueError("Only students enrolled in this course can be on a makeup list.")
    t.allowed_students.set(wanted)
    audit(actor=actor, action="test.makeup_students", obj=t,
          detail={"count": len(wanted)})
    return t


def start_test(t, *, actor):
    """Opens the test. Students can join from this moment - no dates."""
    if t.results_released_at:
        raise ValueError("Results are already out.")
    if t.started_at:
        raise ValueError("The test has already started.")
    for s in t.sections():
        if s["n"] <= 0:
            continue
        pool = t.questions.filter(kind=s["kind"]).count()
        if pool < s["n"]:
            raise ValueError(
                f"Not enough questions in the {s['label']} section: "
                f"you want to draw {s['n']} but the pool has {pool}."
            )
    t.started_at = timezone.now()
    t.save(update_fields=["started_at"])
    audit(actor=actor, action="test.open", obj=t)
    return t


def close_test(t, *, actor):
    """Stops new joins. Students already writing keep their own timers."""
    if not t.started_at:
        raise ValueError("Start the test first.")
    if t.closed_at:
        raise ValueError("The test is already closed.")
    t.closed_at = timezone.now()
    t.save(update_fields=["closed_at"])
    audit(actor=actor, action="test.close", obj=t)
    return t


def reopen_test(t, *, actor):
    """Opens the door again after a close. Released stays closed for good."""
    if t.results_released_at:
        raise ValueError("Results are already out - a released test stays closed.")
    if not t.started_at:
        raise ValueError("Start the test first.")
    if not t.closed_at:
        raise ValueError("The test is not closed.")
    t.closed_at = None
    t.save(update_fields=["closed_at"])
    audit(actor=actor, action="test.reopen", obj=t)
    return t


def archive_test(t, *, actor):
    """Hides the test from everyone, including join by code. Restorable."""
    t.is_active = False
    t.save(update_fields=["is_active"])
    audit(actor=actor, action="test.archive", obj=t)
    return t


def restore_test(t, *, actor):
    t.is_active = True
    t.save(update_fields=["is_active"])
    audit(actor=actor, action="test.restore", obj=t)
    return t


def add_question(t, *, actor, kind, text, options="", answer_key="", accepted_answers=""):
    if t.started_at:
        raise ValueError("Questions are locked once the test has started.")
    opts = [o.strip() for o in options.splitlines() if o.strip()]
    if kind == Question.Kind.MCQ:
        if not (2 <= len(opts) <= 6):
            raise ValueError("A multiple choice question needs 2 to 6 options.")
        if answer_key.strip().upper() not in [chr(65 + i) for i in range(len(opts))]:
            raise ValueError("Pick which option is the answer key.")
    elif kind == Question.Kind.TF:
        if answer_key.strip().upper() not in ("TRUE", "FALSE"):
            raise ValueError("A true/false question needs a True or False key.")
    else:
        variants = [a.strip() for a in accepted_answers.splitlines() if a.strip()]
        if not (1 <= len(variants) <= 5):
            raise ValueError("Give 1 to 5 accepted answers for a short answer question.")
        accepted_answers = "\n".join(variants)
    q = Question.objects.create(
        test=t, kind=kind, text=text.strip(), options="\n".join(opts),
        answer_key=answer_key.strip().upper(), accepted_answers=accepted_answers,
        order=t.questions.count(),
    )
    audit(actor=actor, action="question.create", obj=t, detail={"question": q.id})
    return q


def delete_question(q, *, actor):
    """The floor is per section: a section keeps at least its draw size."""
    t = q.test
    if t.started_at:
        raise ValueError("Questions are locked once the test has started.")
    n_for_kind = {"mcq": t.n_objective, "tf": t.n_tf, "short": t.n_subjective}[q.kind]
    pool = t.questions.filter(kind=q.kind).count()
    if pool <= n_for_kind:
        raise ValueError(
            "Each section needs at least as many questions as you draw. "
            "Lower the draw in Edit settings first."
        )
    q.delete()
    audit(actor=actor, action="question.delete", obj=t)


def join_state(t, *, student, now=None):
    """The states the join page can be in, plus release."""
    now = now or timezone.now()
    attempt = Attempt.objects.filter(test=t, student=student).first()
    if t.results_released_at:
        return "released", attempt
    if attempt:
        if attempt.submitted_at:
            return "submitted", attempt
        deadline = attempt.deadline()
        if deadline and now <= deadline + timedelta(seconds=GRACE_SECONDS):
            return "in_progress", attempt
        return "submitted", attempt  # out of time; finalize() seals it
    if not t.started_at:
        return "upcoming", attempt
    if t.closed_at:
        return "closed", attempt
    return "open", attempt


def student_role(student, t):
    from courses.access import user_role_in_course
    return user_role_in_course(student, t.course)


@transaction.atomic
def start_attempt(t, *, student):
    """The draw is fixed here, section by section. Retry-safe: an existing
    attempt is returned as-is (the unique constraint backstops races)."""
    attempt = Attempt.objects.filter(test=t, student=student).first()
    if attempt:
        return attempt
    now = timezone.now()
    if not t.started_at or t.closed_at or t.results_released_at:
        raise ValueError("This test is not open right now.")
    if student_role(student, t) != "student":
        raise ValueError("Only enrolled students can take this test.")
    if t.is_makeup and not t.allowed_students.filter(pk=student.pk).exists():
        raise ValueError("You are not on the list for this makeup test.")
    drawn = []
    first = None
    expiries = {}
    for s in t.sections():
        if s["n"] <= 0:
            continue
        ids = list(
            t.questions.filter(kind=s["kind"]).order_by("?").values_list("id", flat=True)[: s["n"]]
        )
        if len(ids) < s["n"]:
            raise ValueError("The lecturer has not finished setting this test.")
        drawn.extend(ids)
        if first is None:
            first = s
            expiries[Attempt.SECTION_FIELD[s["key"]]] = now + timedelta(
                seconds=s["n"] * s["seconds"]
            )
    attempt = Attempt.objects.create(
        test=t, student=student, drawn_ids=",".join(str(i) for i in drawn),
        current_section=first["key"], section_started_at=now, **expiries,
    )
    audit(actor=student, action="attempt.start", obj=t)
    return attempt


def advance_section(attempt):
    """Move to the next section, or submit when the last one is done.

    Moving early is the student's choice; time already spent is not refunded
    and the section just left is sealed for good."""
    if attempt.submitted_at:
        return attempt
    t = attempt.test
    sections = t.active_sections()
    keys = [s["key"] for s in sections]
    idx = keys.index(attempt.current_section)
    now = timezone.now()
    if idx == len(sections) - 1:
        deadline = attempt.deadline()
        attempt.submitted_at = min(now, (deadline or now) + timedelta(seconds=GRACE_SECONDS))
        attempt.save(update_fields=["submitted_at"])
        audit(actor=attempt.student, action="test.submit", obj=t)
        return attempt
    nxt = sections[idx + 1]
    attempt.current_section = nxt["key"]
    attempt.section_started_at = now
    setattr(attempt, Attempt.SECTION_FIELD[nxt["key"]],
            now + timedelta(seconds=nxt["n"] * nxt["seconds"]))
    attempt.save()
    audit(actor=attempt.student, action="attempt.advance", obj=t)
    return attempt


def save_answer(attempt, *, question_id, choice="", text=""):
    """Idempotent upsert for autosave. Only the live section, only in time."""
    now = timezone.now()
    if attempt.submitted_at:
        raise ValueError("The test is already submitted.")
    deadline = attempt.deadline()
    if deadline and now > deadline + timedelta(seconds=GRACE_SECONDS):
        raise ValueError("Time is up for this section.")
    target = next((q for q in attempt.drawn_questions() if q.id == int(question_id)), None)
    if target is None:
        raise ValueError("That question is not part of your attempt.")
    if SECTION_OF_KIND[target.kind] != attempt.current_section:
        raise ValueError("That section is not open right now.")
    answer, _ = Answer.objects.update_or_create(
        attempt=attempt, question_id=int(question_id),
        defaults={"choice": (choice or "").strip().upper()[:10], "text": (text or "")[:2000]},
    )
    return answer


def finalize(attempt, force=False):
    """Seal an unsubmitted attempt. Lazy path: past the current section's
    deadline + grace, sealed by the next read. Forced path: results release
    seals running attempts now."""
    deadline = attempt.deadline()
    if deadline is None:
        return attempt
    now = timezone.now()
    if attempt.submitted_at is None and (force or now > deadline + timedelta(seconds=GRACE_SECONDS)):
        attempt.submitted_at = min(now, deadline + timedelta(seconds=GRACE_SECONDS))
        attempt.save(update_fields=["submitted_at"])
        audit(actor=None, action="test.autosubmit", obj=attempt.test,
              detail={"attempt": attempt.id})
    return attempt


def submit(attempt, *, force=False):
    now = timezone.now()
    if attempt.submitted_at:
        return attempt
    deadline = attempt.deadline()
    if not force and (deadline is None or now > deadline + timedelta(seconds=GRACE_SECONDS)):
        raise ValueError("Time is up for this section.")
    attempt.submitted_at = min(now, (deadline or now) + timedelta(seconds=GRACE_SECONDS))
    attempt.save(update_fields=["submitted_at"])
    audit(actor=attempt.student, action="test.submit", obj=attempt.test)
    return attempt


def clone_test(t, *, actor):
    """Copy settings and questions into a fresh draft with a new join code.
    Attempts, results and lifecycle stay with the original."""
    c = Test(
        course=t.course, title=f"{t.title} (copy)",
        n_objective=t.n_objective, n_tf=t.n_tf, n_subjective=t.n_subjective,
        seconds_objective=t.seconds_objective, seconds_tf=t.seconds_tf,
        seconds_subjective=t.seconds_subjective,
        points_per_question=t.points_per_question, is_makeup=t.is_makeup,
        created_by=actor,
    )
    for _ in range(20):
        candidate = make_join_code()
        if not Test.objects.filter(join_code=candidate).exists():
            c.join_code = candidate
            break
    c.save()
    if t.is_makeup:
        c.allowed_students.set(t.allowed_students.all())
    for q in t.questions.all():
        Question.objects.create(
            test=c, kind=q.kind, text=q.text, options=q.options,
            answer_key=q.answer_key, accepted_answers=q.accepted_answers, order=q.order,
        )
    audit(actor=actor, action="test.clone", obj=c, detail={"source": t.id})
    return c


def release_results(t, *, actor):
    """One action, to everyone. Also closes the test permanently."""
    if t.results_released_at:
        raise ValueError("Results are already out.")
    if not t.started_at:
        raise ValueError("Start the test before releasing results.")
    for a in t.attempts.filter(submitted_at__isnull=True):
        finalize(a, force=True)
    t.results_released_at = timezone.now()
    updates = ["results_released_at"]
    if not t.closed_at:
        t.closed_at = t.results_released_at
        updates.append("closed_at")
    t.save(update_fields=updates)
    audit(actor=actor, action="test.release", obj=t)
    return t
