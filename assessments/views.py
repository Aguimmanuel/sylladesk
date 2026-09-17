from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from courses.access import is_staff_of, user_role_in_course
from courses.views import _course_or_404

from .forms import JoinForm, QuestionForm, TestForm
from .grading import grade_objective, grade_subjective
from .models import Attempt, Question, Test
from . import services


def _test_or_404(course_id, test_id):
    return get_object_or_404(Test, pk=test_id, course_id=course_id, is_active=True)


def _test_by_code(code):
    return get_object_or_404(Test, join_code=code.strip().upper(), is_active=True)


def _staff_test(request, course_id, test_id):
    """Course staff guard shared by the lecturer routes."""
    course = _course_or_404(course_id)
    t = _test_or_404(course_id, test_id)
    if not is_staff_of(request.user, course):
        return course, t, False
    return course, t, True


def _review_rows(attempt):
    """Per-question verdicts for the lecturer's attempt page and the
    student's own review after release."""
    answers = {a.question_id: a for a in attempt.answers.all()}
    rows = []
    for q in attempt.drawn_questions():
        row = {"q": q, "given": "—", "key": "—", "verdict": "blank"}
        if q.kind == "mcq":
            opts = q.option_list()

            def opt_text(letter):
                i = ord(letter) - 65
                return f"{letter} — {opts[i]}" if 0 <= i < len(opts) else letter

            row["key"] = opt_text(q.answer_key.strip().upper())
            if answers.get(q.id) and answers[q.id].choice:
                row["given"] = opt_text(answers[q.id].choice.strip().upper())
                row["verdict"] = "correct" if grade_objective(q, answers[q.id].choice) else "wrong"
        elif q.kind == "tf":
            row["key"] = q.answer_key.strip().upper().capitalize()
            if answers.get(q.id) and answers[q.id].choice:
                row["given"] = answers[q.id].choice.strip().upper().capitalize()
                row["verdict"] = "correct" if grade_objective(q, answers[q.id].choice) else "wrong"
        else:
            row["key"] = ", ".join(
                s.strip() for s in q.accepted_answers.splitlines() if s.strip()
            ) or "—"
            if answers.get(q.id) and answers[q.id].text.strip():
                row["given"] = answers[q.id].text.strip()
                row["verdict"] = "correct" if grade_subjective(q, answers[q.id].text) else "wrong"
        rows.append(row)
    return rows


@login_required
def create(request, course_id):
    course = _course_or_404(course_id)
    if not is_staff_of(request.user, course):
        messages.error(request, "Only course staff can create tests.")
        return redirect("courses:detail", course_id=course.id)
    form = TestForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            t = services.create_test(
                course, actor=request.user, title=form.cleaned_data["title"],
                n_objective=form.cleaned_data["n_objective"],
                n_tf=form.cleaned_data["n_tf"],
                n_subjective=form.cleaned_data["n_subjective"],
                seconds_objective=form.cleaned_data["seconds_objective"],
                seconds_tf=form.cleaned_data["seconds_tf"],
                seconds_subjective=form.cleaned_data["seconds_subjective"],
                points_per_question=form.cleaned_data["points_per_question"],
            )
        except ValueError as e:
            form.add_error(None, str(e))
        else:
            messages.success(request, f"Test created. Join code: {t.join_code}")
            return redirect("assessments:detail", course_id=course.id, test_id=t.id)
    return render(request, "assessments/create.html", {
        "course": course, "form": form, "editing": False,
        "pool_mcq": 0, "pool_tf": 0, "pool_short": 0,
    })


@login_required
def edit(request, course_id, test_id):
    course = _course_or_404(course_id)
    t = _test_or_404(course_id, test_id)
    if not is_staff_of(request.user, course):
        messages.error(request, "Only course staff can edit tests.")
        return redirect("courses:detail", course_id=course.id)
    if t.started_at or t.results_released_at:
        messages.error(request, "Settings are locked once the test has started.")
        return redirect("assessments:detail", course_id=course.id, test_id=t.id)
    form = TestForm(request.POST or None, instance=t)
    if request.method == "POST" and form.is_valid():
        fields = ("title", "n_objective", "n_tf", "n_subjective", "seconds_objective",
                  "seconds_tf", "seconds_subjective", "points_per_question")
        try:
            services.update_settings(t, actor=request.user,
                                     **{f: form.cleaned_data[f] for f in fields})
        except ValueError as e:
            form.add_error(None, str(e))
        else:
            messages.success(request, "Settings saved.")
            return redirect("assessments:detail", course_id=course.id, test_id=t.id)
    return render(request, "assessments/create.html", {
        "course": course, "form": form, "editing": True, "test": t,
        "pool_mcq": t.questions.filter(kind="mcq").count(),
        "pool_tf": t.questions.filter(kind="tf").count(),
        "pool_short": t.questions.filter(kind="short").count(),
    })


@login_required
def detail(request, course_id, test_id):
    course = _course_or_404(course_id)
    t = _test_or_404(course_id, test_id)
    if not is_staff_of(request.user, course):
        return redirect("assessments:join", code=t.join_code)
    locked = bool(t.started_at or t.results_released_at)
    context = {
        "course": course, "test": t, "questions": t.questions.all(),
        "qform": QuestionForm(), "locked": locked,
        "attempts": t.attempts.count(),
        "submitted": t.attempts.filter(submitted_at__isnull=False).count(),
        "attempts_list": t.attempts.select_related("student").order_by("started_at"),
    }
    return render(request, "assessments/detail.html", context)


@login_required
@require_POST
def start(request, course_id, test_id):
    course, t, allowed = _staff_test(request, course_id, test_id)
    if not allowed:
        return redirect("courses:detail", course_id=course.id)
    try:
        services.start_test(t, actor=request.user)
    except ValueError as e:
        messages.error(request, str(e))
    else:
        messages.success(request, "The test has started. Students can join now.")
    return redirect("assessments:detail", course_id=course.id, test_id=t.id)


@login_required
@require_POST
def close(request, course_id, test_id):
    course, t, allowed = _staff_test(request, course_id, test_id)
    if not allowed:
        return redirect("courses:detail", course_id=course.id)
    try:
        services.close_test(t, actor=request.user)
    except ValueError as e:
        messages.error(request, str(e))
    else:
        messages.success(request, "The test is closed. Students already writing can finish.")
    return redirect("assessments:detail", course_id=course.id, test_id=t.id)


@login_required
@require_POST
def reopen(request, course_id, test_id):
    course, t, allowed = _staff_test(request, course_id, test_id)
    if not allowed:
        return redirect("courses:detail", course_id=course.id)
    try:
        services.reopen_test(t, actor=request.user)
    except ValueError as e:
        messages.error(request, str(e))
    else:
        messages.success(request, "The test is open again. Students can join.")
    return redirect("assessments:detail", course_id=course.id, test_id=t.id)


@login_required
@require_POST
def archive(request, course_id, test_id):
    course, t, allowed = _staff_test(request, course_id, test_id)
    if not allowed:
        return redirect("courses:detail", course_id=course.id)
    services.archive_test(t, actor=request.user)
    messages.success(request, "Test removed. You can bring it back from the course page.")
    return redirect("courses:detail", course_id=course.id)


@login_required
@require_POST
def restore(request, course_id, test_id):
    course, t, allowed = _staff_test(request, course_id, test_id)
    if not allowed:
        return redirect("courses:detail", course_id=course.id)
    services.restore_test(t, actor=request.user)
    messages.success(request, "Test restored.")
    return redirect("courses:detail", course_id=course.id)


@login_required
@require_POST
def add_question(request, course_id, test_id):
    course, t, allowed = _staff_test(request, course_id, test_id)
    if not allowed:
        return redirect("courses:detail", course_id=course.id)
    form = QuestionForm(request.POST)
    if form.is_valid():
        try:
            services.add_question(t, actor=request.user, kind=form.cleaned_data["kind"],
                         text=form.cleaned_data["text"], options=form.cleaned_data["options"],
                         answer_key=form.cleaned_data["answer_key"],
                         accepted_answers=form.cleaned_data["accepted_answers"])
            messages.success(request, "Question added.")
        except ValueError as e:
            messages.error(request, str(e))
    return redirect("assessments:detail", course_id=course.id, test_id=t.id)


@login_required
@require_POST
def delete_question(request, course_id, test_id, question_id):
    course, t, allowed = _staff_test(request, course_id, test_id)
    if not allowed:
        return redirect("courses:detail", course_id=course.id)
    q = get_object_or_404(Question, pk=question_id, test=t)
    try:
        services.delete_question(q, actor=request.user)
        messages.success(request, "Question removed.")
    except ValueError as e:
        messages.error(request, str(e))
    return redirect("assessments:detail", course_id=course.id, test_id=t.id)


@login_required
@require_POST
def regenerate(request, course_id, test_id):
    course, t, allowed = _staff_test(request, course_id, test_id)
    if not allowed:
        return redirect("courses:detail", course_id=course.id)
    services.regenerate_join_code(t, actor=request.user)
    messages.success(request, f"New join code: {t.join_code}. The old code no longer works.")
    return redirect("assessments:detail", course_id=course.id, test_id=t.id)


@login_required
@require_POST
def release(request, course_id, test_id):
    course, t, allowed = _staff_test(request, course_id, test_id)
    if not allowed:
        return redirect("courses:detail", course_id=course.id)
    try:
        services.release_results(t, actor=request.user)
    except ValueError as e:
        messages.error(request, str(e))
    else:
        messages.success(request, "Results are out. The test is closed for good.")
    return redirect("assessments:detail", course_id=course.id, test_id=t.id)


@login_required
@require_POST
def join_box(request):
    code = request.POST.get("code", "").strip().upper()
    if len(code) != 6:
        messages.error(request, "Join codes are 6 characters.")
        return redirect("courses:list")
    return redirect("assessments:join", code=code)


@login_required
def join(request, code):
    t = _test_by_code(code)
    role = user_role_in_course(request.user, t.course)
    if role is None:
        messages.error(request, "That code is for students enrolled in the course.")
        return redirect("courses:list")
    state, attempt = services.join_state(t, student=request.user)
    if attempt and state != "released":
        services.finalize(attempt)
    score = attempt.score() if (attempt and t.results_released_at) else None
    review = _review_rows(attempt) if (attempt and t.results_released_at) else None
    return render(request, "assessments/join.html", {
        "test": t, "state": state, "attempt": attempt, "score": score, "review": review,
        "now": timezone.now(),
    })


@login_required
def take(request, code):
    t = _test_by_code(code)
    state, attempt = services.join_state(t, student=request.user)
    if state in ("upcoming", "closed", "released"):
        return redirect("assessments:join", code=code)
    if not attempt:
        try:
            attempt = services.start_attempt(t, student=request.user)
        except ValueError as e:
            messages.error(request, str(e))
            return redirect("assessments:join", code=code)
    else:
        services.finalize(attempt)
        attempt.refresh_from_db()
    if attempt.submitted_at:
        return redirect("assessments:join", code=code)
    sections = t.active_sections()
    keys = [s["key"] for s in sections]
    key = attempt.current_section
    idx = keys.index(key)
    grouped = attempt.section_questions()
    deadline = attempt.deadline()
    return render(request, "assessments/take.html", {
        "test": t, "attempt": attempt,
        "questions": grouped[key],
        "answers": {a.question_id: a for a in attempt.answers.all()},
        "expires_epoch": int(deadline.timestamp()) if deadline else 0,
        "section_number": idx + 1,
        "section_total": len(sections),
        "section_label": sections[idx]["label"],
        "is_last": idx == len(sections) - 1,
    })


@login_required
@require_POST
def save(request, code):
    t = _test_by_code(code)
    attempt = Attempt.objects.filter(test=t, student=request.user).first()
    if not attempt:
        raise Http404()
    try:
        services.save_answer(attempt, question_id=request.POST.get("question"),
                    choice=request.POST.get("choice", ""),
                    text=request.POST.get("text", ""))
    except ValueError as e:
        if request.headers.get("x-requested-with") == "fetch":
            return JsonResponse({"ok": False, "error": str(e)}, status=400)
        messages.error(request, str(e))
        return redirect("assessments:join", code=code)
    if request.headers.get("x-requested-with") == "fetch":
        return JsonResponse({"ok": True})
    messages.success(request, "Answer saved.")
    return redirect("assessments:take", code=code)


@login_required
@require_POST
def advance(request, code):
    t = _test_by_code(code)
    attempt = Attempt.objects.filter(test=t, student=request.user).first()
    if not attempt:
        raise Http404()
    services.finalize(attempt)
    attempt.refresh_from_db()
    if not attempt.submitted_at:
        services.advance_section(attempt)
    return redirect("assessments:take", code=code)


@login_required
@require_POST
def submit_test(request, code):
    t = _test_by_code(code)
    attempt = Attempt.objects.filter(test=t, student=request.user).first()
    if not attempt:
        raise Http404()
    try:
        services.submit(attempt)
    except ValueError as e:
        messages.error(request, str(e))
        services.finalize(attempt)
    return redirect("assessments:join", code=code)


@login_required
def status(request, code):
    """Polled by the join page so it flips over by itself when the
    lecturer starts the test."""
    t = _test_by_code(code)
    if user_role_in_course(request.user, t.course) is None:
        raise Http404()
    state, _ = services.join_state(t, student=request.user)
    return JsonResponse({"state": state})


@login_required
def attempt_detail(request, course_id, test_id, attempt_id):
    course, t, allowed = _staff_test(request, course_id, test_id)
    if not allowed:
        return redirect("courses:detail", course_id=course.id)
    attempt = get_object_or_404(Attempt, pk=attempt_id, test=t)
    services.finalize(attempt)
    return render(request, "assessments/attempt.html", {
        "course": course, "test": t, "attempt": attempt,
        "rows": _review_rows(attempt),
    })


@login_required
def attempts_fragment(request, course_id, test_id):
    """HTML fragment of the Attempts section. The test page polls it while
    the test runs, so new starters and submissions appear without a reload."""
    course, t, allowed = _staff_test(request, course_id, test_id)
    if not allowed:
        return redirect("courses:detail", course_id=course.id)
    return render(request, "assessments/_attempts.html", {
        "test": t,
        "attempts": t.attempts.count(),
        "submitted": t.attempts.filter(submitted_at__isnull=False).count(),
        "attempts_list": t.attempts.select_related("student").order_by("started_at"),
    })


@login_required
@require_POST
def clone(request, course_id, test_id):
    course, t, allowed = _staff_test(request, course_id, test_id)
    if not allowed:
        return redirect("courses:detail", course_id=course.id)
    c = services.clone_test(t, actor=request.user)
    messages.success(request, "Cloned. The copy is a draft — edit its settings and questions freely.")
    return redirect("assessments:detail", course_id=course.id, test_id=c.id)
