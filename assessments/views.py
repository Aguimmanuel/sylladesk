from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from core.auditing import audit
from courses.access import is_staff_of, user_role_in_course
from courses.views import _course_or_404

from .forms import JoinForm, QuestionForm, TestForm
from .models import Answer, Attempt, Question, Test
from .services import (finalize, join_state, regenerate_join_code, release_results,
                       save_answer, start_attempt, submit, create_test, add_question,
                       delete_question)


def _test_or_404(course_id, test_id):
    return get_object_or_404(Test, pk=test_id, course_id=course_id, is_active=True)


def _test_by_code(code):
    return get_object_or_404(Test, join_code=code.strip().upper(), is_active=True)


@login_required
def create(request, course_id):
    course = _course_or_404(course_id)
    if not is_staff_of(request.user, course):
        messages.error(request, "Only course staff can create tests.")
        return redirect("courses:detail", course_id=course.id)
    form = TestForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            t = create_test(
                course, actor=request.user, title=form.cleaned_data["title"],
                open_at=form.cleaned_data["open_at"], close_at=form.cleaned_data["close_at"],
                n_to_answer=form.cleaned_data["n_to_answer"],
                points_per_question=form.cleaned_data["points_per_question"],
                allow_review=form.cleaned_data["allow_review"],
            )
        except ValueError as e:
            form.add_error(None, str(e))
        else:
            messages.success(request, f"Test created. Join code: {t.join_code}")
            return redirect("assessments:detail", course_id=course.id, test_id=t.id)
    return render(request, "assessments/create.html", {"course": course, "form": form})


@login_required
def detail(request, course_id, test_id):
    course = _course_or_404(course_id)
    t = _test_or_404(course_id, test_id)
    if not is_staff_of(request.user, course):
        return redirect("assessments:join", code=t.join_code)
    context = {
        "course": course, "test": t, "questions": t.questions.all(),
        "qform": QuestionForm(), "attempts": t.attempts.count(),
        "submitted": t.attempts.filter(submitted_at__isnull=False).count(),
    }
    return render(request, "assessments/detail.html", context)


@login_required
@require_POST
def add_question(request, course_id, test_id):
    course = _course_or_404(course_id)
    t = _test_or_404(course_id, test_id)
    if not is_staff_of(request.user, course):
        return redirect("courses:detail", course_id=course.id)
    form = QuestionForm(request.POST)
    if form.is_valid():
        try:
            add_question(t, actor=request.user, kind=form.cleaned_data["kind"],
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
    course = _course_or_404(course_id)
    t = _test_or_404(course_id, test_id)
    if not is_staff_of(request.user, course):
        return redirect("courses:detail", course_id=course.id)
    q = get_object_or_404(Question, pk=question_id, test=t)
    try:
        delete_question(q, actor=request.user)
        messages.success(request, "Question removed.")
    except ValueError as e:
        messages.error(request, str(e))
    return redirect("assessments:detail", course_id=course.id, test_id=t.id)


@login_required
@require_POST
def regenerate(request, course_id, test_id):
    course = _course_or_404(course_id)
    t = _test_or_404(course_id, test_id)
    if not is_staff_of(request.user, course):
        return redirect("courses:detail", course_id=course.id)
    regenerate_join_code(t, actor=request.user)
    messages.success(request, f"New join code: {t.join_code}. The old code no longer works.")
    return redirect("assessments:detail", course_id=course.id, test_id=t.id)


@login_required
@require_POST
def release(request, course_id, test_id):
    course = _course_or_404(course_id)
    t = _test_or_404(course_id, test_id)
    if not is_staff_of(request.user, course):
        return redirect("courses:detail", course_id=course.id)
    try:
        release_results(t, actor=request.user)
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
    state, attempt = join_state(t, student=request.user)
    if attempt and state != "released":
        finalize(attempt)
    score = attempt.score() if (attempt and t.results_released_at) else None
    return render(request, "assessments/join.html", {
        "test": t, "state": state, "attempt": attempt, "score": score,
        "now": timezone.now(),
    })


@login_required
def take(request, code):
    t = _test_by_code(code)
    state, attempt = join_state(t, student=request.user)
    if state == "upcoming" or state == "closed":
        return redirect("assessments:join", code=code)
    if not attempt:
        try:
            attempt = start_attempt(t, student=request.user)
        except ValueError as e:
            messages.error(request, str(e))
            return redirect("assessments:join", code=code)
    else:
        finalize(attempt)
        attempt.refresh_from_db()
    if attempt.submitted_at:
        return redirect("assessments:join", code=code)
    answers = {a.question_id: a for a in attempt.answers.all()}
    return render(request, "assessments/take.html", {
        "test": t, "attempt": attempt, "questions": attempt.drawn_questions(),
        "answers": answers,
        "expires_epoch": int(attempt.expires_at.timestamp()),
    })


@login_required
@require_POST
def save(request, code):
    t = _test_by_code(code)
    attempt = Attempt.objects.filter(test=t, student=request.user).first()
    if not attempt:
        raise Http404()
    try:
        save_answer(attempt, question_id=request.POST.get("question"),
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
def submit_test(request, code):
    t = _test_by_code(code)
    attempt = Attempt.objects.filter(test=t, student=request.user).first()
    if not attempt:
        raise Http404()
    try:
        submit(attempt)
    except ValueError as e:
        messages.error(request, str(e))
        finalize(attempt)
    return redirect("assessments:join", code=code)
