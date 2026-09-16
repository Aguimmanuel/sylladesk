"""Test lifecycle rules. The server clock is the only clock."""
import secrets
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from core.auditing import audit

from .models import Answer, Attempt, Question, Test, make_join_code

SUBMIT_GRACE_SECONDS = 10  # submissions in flight at expiry still count


def validate_test_window(*, open_at, close_at):
    if close_at <= open_at:
        raise ValueError("The closing time must be after the opening time.")
    if close_at <= timezone.now():
        raise ValueError("The closing time must be in the future.")


def create_test(course, *, actor, title, open_at, close_at, n_to_answer,
                points_per_question=1, allow_review=False):
    if n_to_answer < 1:
        raise ValueError("A test must require at least one question.")
    validate_test_window(open_at=open_at, close_at=close_at)
    t = Test(
        course=course, title=title.strip(), open_at=open_at, close_at=close_at,
        join_code=make_join_code(), n_to_answer=n_to_answer,
        points_per_question=points_per_question, allow_review=allow_review,
        created_by=actor,
    )
    t.save()
    audit(actor=actor, action="test.create", obj=t)
    return t


def regenerate_join_code(t, *, actor):
    """Leak response: the old code dies instantly; running attempts are
    unaffected because they are bound to the attempt, not the code."""
    old = t.join_code
    for _ in range(20):
        candidate = make_join_code()
        if candidate != old and not Test.objects.filter(join_code=candidate).exists():
            t.join_code = candidate
            t.save(update_fields=["join_code"])
            break
    audit(actor=actor, action="test.regen_code", obj=t, detail={"old": old, "new": t.join_code})
    return t


def add_question(t, *, actor, kind, text, options="", answer_key="", accepted_answers=""):
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
    """Refuses only when the question pool would drop below N to answer."""
    t = q.test
    if t.questions.count() <= t.n_to_answer:
        raise ValueError("The pool cannot go below the number of questions to answer.")
    q.delete()
    audit(actor=actor, action="question.delete", obj=t)


def join_state(t, *, student, now=None):
    """The five states the join page can be in, plus release."""
    now = now or timezone.now()
    attempt = Attempt.objects.filter(test=t, student=student).first()
    if t.results_released_at:
        return "released", attempt
    if now < t.open_at:
        return "upcoming", attempt
    if attempt and attempt.submitted_at:
        return "submitted", attempt
    if attempt and now < attempt.expires_at:
        return "in_progress", attempt
    if attempt:
        return "submitted", attempt  # ran out of time; finalize() marks it
    if now > t.close_at:
        return "closed", attempt
    return "open", attempt


@transaction.atomic
def start_attempt(t, *, student):
    """The draw and expiry are fixed here. Retry-safe: an existing attempt
    is returned as-is (the unique constraint backstops races)."""
    attempt = Attempt.objects.filter(test=t, student=student).first()
    if attempt:
        return attempt
    now = timezone.now()
    if now < t.open_at or now > t.close_at:
        raise ValueError("This test is not open right now.")
    if t.questions.count() < t.n_to_answer:
        raise ValueError("The lecturer has not finished setting this test.")
    if student_role(student, t) != "student":
        raise ValueError("Only enrolled students can take this test.")
    drawn = list(t.questions.order_by("?").values_list("id", flat=True)[: t.n_to_answer])
    seconds = 0
    for kind in Question.objects.filter(id__in=drawn).values_list("kind", flat=True):
        seconds += t.seconds_subjective if kind == Question.Kind.SHORT else t.seconds_objective
    attempt = Attempt.objects.create(
        test=t, student=student, drawn_ids=",".join(str(i) for i in drawn),
        expires_at=now + timedelta(seconds=seconds),
    )
    audit(actor=student, action="test.start", obj=t)
    return attempt


def student_role(student, t):
    from courses.access import user_role_in_course
    return user_role_in_course(student, t.course)


def save_answer(attempt, *, question_id, choice="", text=""):
    """Idempotent upsert for autosave. Refused once time is up."""
    now = timezone.now()
    if attempt.submitted_at or now > attempt.expires_at:
        raise ValueError("Time is up for this test.")
    if int(question_id) not in [q.id for q in attempt.drawn_questions()]:
        raise ValueError("That question is not part of your attempt.")
    answer, _ = Answer.objects.update_or_create(
        attempt=attempt, question_id=int(question_id),
        defaults={"choice": (choice or "").strip().upper()[:10], "text": (text or "")[:2000]},
    )
    return answer


def finalize(attempt, force=False):
    """Seal an unsubmitted attempt. Lazy path: past expiry + grace, sealed by
    the next read. Forced path: results release seals running attempts now."""
    now = timezone.now()
    if attempt.submitted_at is None and (force or now > attempt.expires_at + timedelta(seconds=SUBMIT_GRACE_SECONDS)):
        attempt.submitted_at = min(now, attempt.expires_at + timedelta(seconds=SUBMIT_GRACE_SECONDS))
        attempt.save(update_fields=["submitted_at"])
        audit(actor=None, action="test.autosubmit", obj=attempt.test,
              detail={"attempt": attempt.id})
    return attempt


def submit(attempt, *, force=False):
    now = timezone.now()
    if attempt.submitted_at:
        return attempt
    if not force and now > attempt.expires_at + timedelta(seconds=SUBMIT_GRACE_SECONDS):
        raise ValueError("Time is up for this test.")
    attempt.submitted_at = min(now, attempt.expires_at + timedelta(seconds=SUBMIT_GRACE_SECONDS))
    attempt.save(update_fields=["submitted_at"])
    audit(actor=attempt.student, action="test.submit", obj=attempt.test)
    return attempt


def release_results(t, *, actor):
    """One action, to everyone. Also closes the test permanently."""
    if t.results_released_at:
        raise ValueError("Results are already out.")
    for a in t.attempts.filter(submitted_at__isnull=True):
        finalize(a, force=True)
    t.results_released_at = timezone.now()
    t.save(update_fields=["results_released_at"])
    audit(actor=actor, action="test.release", obj=t)
    return t

