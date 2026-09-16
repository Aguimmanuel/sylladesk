import smtplib
from logging import getLogger

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from core.auditing import audit
from core.storage import get_storage
from courses.access import is_staff_of, user_role_in_course
from courses.models import Course
from courses.views import _course_or_404

from .forms import AssignmentForm, GradeForm, SubmissionForm
from .models import Assignment, Submission
from .services import (deadline_with_grace, grade_submission, roster_status,
                       submit_assignment, update_assignment)

logger = getLogger(__name__)


def _assignment_or_404(course_id, assignment_id):
    return get_object_or_404(
        Assignment, pk=assignment_id, course_id=course_id, is_active=True
    )


@login_required
def create(request, course_id):
    course = _course_or_404(course_id)
    if not is_staff_of(request.user, course):
        messages.error(request, "Only course staff can create assignments.")
        return redirect("courses:detail", course_id=course.id)
    form = AssignmentForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            a = form.save(commit=False)
            a.course = course
            a.created_by = request.user
            a.save()
        except ValueError as e:
            form.add_error(None, str(e))
        else:
            audit(actor=request.user, action="assignment.create", obj=a)
            messages.success(request, f"Assignment “{a.title}” posted.")
            return redirect("assignments:detail", course_id=course.id, assignment_id=a.id)
    return render(request, "assignments/create.html", {"course": course, "form": form})


@login_required
def edit(request, course_id, assignment_id):
    course = _course_or_404(course_id)
    a = _assignment_or_404(course_id, assignment_id)
    if not is_staff_of(request.user, course):
        messages.error(request, "Only course staff can edit assignments.")
        return redirect("courses:detail", course_id=course.id)
    form = AssignmentForm(request.POST or None, instance=a)
    if request.method == "POST" and form.is_valid():
        try:
            update_assignment(a, actor=request.user, data={
                f: form.cleaned_data[f] for f in form.cleaned_data
            })
        except ValueError as e:
            messages.error(request, str(e))
            return redirect("assignments:detail", course_id=course.id, assignment_id=a.id)
        messages.success(request, "Assignment updated.")
        return redirect("assignments:detail", course_id=course.id, assignment_id=a.id)
    return render(request, "assignments/edit.html", {"course": course, "assignment": a, "form": form})


@login_required
def detail(request, course_id, assignment_id):
    course = _course_or_404(course_id)
    a = _assignment_or_404(course_id, assignment_id)
    role = user_role_in_course(request.user, course)
    if role is None:
        messages.error(request, "You are not enrolled in this course.")
        return redirect("courses:list")
    closed = timezone.now() > deadline_with_grace(a)
    mine = a.submissions.filter(student=request.user).order_by("attempt_no")
    context = {
        "course": course, "assignment": a, "closed": closed,
        "is_staff": is_staff_of(request.user, course),
    }
    if context["is_staff"]:
        context["rows"] = roster_status(a)
    else:
        context["mine"] = mine
        context["form"] = SubmissionForm()
        already_graded = mine.filter(graded_at__isnull=False).exists()
        context["already_graded"] = already_graded
        context["can_submit"] = (role == "student" and not closed and not already_graded)
    return render(request, "assignments/detail.html", context)


@login_required
@require_POST
def submit(request, course_id, assignment_id):
    course = _course_or_404(course_id)
    a = _assignment_or_404(course_id, assignment_id)
    if user_role_in_course(request.user, course) != "student":
        messages.error(request, "Only enrolled students can submit.")
        return redirect("assignments:detail", course_id=course.id, assignment_id=a.id)
    form = SubmissionForm(request.POST, request.FILES)
    if not form.is_valid():
        for errs in form.errors.values():
            for e in errs:
                messages.error(request, e)
        return redirect("assignments:detail", course_id=course.id, assignment_id=a.id)
    try:
        s = submit_assignment(a, student=request.user,
                              uploaded=request.FILES["submission_file"],
                              note=form.cleaned_data.get("note", ""))
    except ValueError as e:
        messages.error(request, str(e))
    else:
        receipt = (f"Receipt — attempt {s.attempt_no} · "
                   f"{timezone.localtime(s.submitted_at):%d %b %Y, %H:%M} WAT · "
                   f"{s.file.original_name} · {s.file.size_bytes:,} bytes · "
                   f"checksum {s.file.sha256[:12]}")
        messages.success(request, receipt + (" — LATE" if s.is_late else ""))
    return redirect("assignments:detail", course_id=course.id, assignment_id=a.id)


def _open_submission(request, course_id, assignment_id, submission_id):
    """Shared gate for view/download: the owning student or course staff."""
    course = _course_or_404(course_id)
    a = _assignment_or_404(course_id, assignment_id)
    s = get_object_or_404(Submission, pk=submission_id, assignment=a)
    if not (is_staff_of(request.user, course) or s.student_id == request.user.id):
        raise Http404()
    return s, get_storage().open(s.file)


@login_required
def submission_view(request, course_id, assignment_id, submission_id):
    """Open a submission in the browser instead of forcing a save."""
    s, fh = _open_submission(request, course_id, assignment_id, submission_id)
    return FileResponse(fh, filename=s.file.original_name)


@login_required
def submission_download(request, course_id, assignment_id, submission_id):
    s, fh = _open_submission(request, course_id, assignment_id, submission_id)
    return FileResponse(fh, as_attachment=True, filename=s.file.original_name)


@login_required
@require_POST
def grade(request, course_id, assignment_id, submission_id):
    course = _course_or_404(course_id)
    a = _assignment_or_404(course_id, assignment_id)
    s = get_object_or_404(Submission, pk=submission_id, assignment=a)
    if not is_staff_of(request.user, course):
        messages.error(request, "Only course staff can grade.")
        return redirect("assignments:detail", course_id=course.id, assignment_id=a.id)
    form = GradeForm(request.POST)
    if form.is_valid():
        try:
            grade_submission(s, actor=request.user,
                             score=form.cleaned_data["score"],
                             note=form.cleaned_data["score_note"])
        except ValueError as e:
            messages.error(request, str(e))
    return redirect("assignments:detail", course_id=course.id, assignment_id=a.id)
