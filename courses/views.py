from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from core.auditing import audit

from .access import is_staff_of, user_role_in_course
from .forms import CourseForm, RosterUploadForm
from .models import Course, RosterEntry
from .services import import_roster

User = get_user_model()


@login_required
def list_courses(request):
    user = request.user
    if user.is_lecturer_role or (user.is_admin_role and not user.is_staff):
        courses = Course.objects.filter(is_active=True, lecturer=user)
    else:
        courses = Course.objects.filter(
            enrollments__user=user, enrollments__is_active=True, is_active=True
        )
    return render(request, "courses/list.html", {"courses": courses})


@login_required
def create_course(request):
    if not (request.user.is_lecturer_role or request.user.is_admin_role):
        messages.error(request, "Only lecturers can create courses.")
        return redirect("courses:list")
    if request.method == "POST":
        form = CourseForm(request.POST)
        if form.is_valid():
            course = form.save(commit=False)
            course.lecturer = request.user if request.user.is_lecturer_role else User.objects.filter(
                global_role=User.GlobalRole.LECTURER).first()
            try:
                course.save()
            except IntegrityError:
                form.add_error(None, "A course with this code already exists for this session.")
            else:
                audit(actor=request.user, action="course.create", obj=course)
                messages.success(request, f"Course {course.code} created.")
                return redirect("courses:detail", course_id=course.id)
    else:
        form = CourseForm()
    return render(request, "courses/create.html", {"form": form})


def _course_or_404(course_id):
    return get_object_or_404(Course, pk=course_id, is_active=True)


@login_required
def detail(request, course_id):
    course = _course_or_404(course_id)
    role = user_role_in_course(request.user, course)
    if role is None:
        messages.error(request, "You are not enrolled in this course.")
        return redirect("courses:list")
    staff = is_staff_of(request.user, course)
    from materials.forms import MaterialForm
    from materials.models import Material
    materials = Material.objects.filter(course=course, is_deleted=False).order_by("week_no", "title")
    roster = RosterEntry.objects.filter(course=course).select_related("claimed_by") if staff else None
    return render(request, "courses/detail.html", {
        "course": course, "role": role, "materials": materials, "roster": roster,
        "is_staff": staff, "mform": MaterialForm() if staff else None,
    })


@login_required
@require_POST
def archive(request, course_id):
    course = _course_or_404(course_id)
    if not is_staff_of(request.user, course):
        messages.error(request, "Not allowed.")
        return redirect("courses:list")
    course.is_active = False
    course.save(update_fields=["is_active"])
    audit(actor=request.user, action="course.archive", obj=course)
    messages.success(request, f"{course.code} archived.")
    return redirect("courses:list")


@login_required
def roster_upload(request, course_id):
    course = _course_or_404(course_id)
    if not is_staff_of(request.user, course):
        messages.error(request, "Not allowed.")
        return redirect("courses:detail", course_id=course.id)
    if request.method == "POST":
        form = RosterUploadForm(request.POST, request.FILES)
        if form.is_valid():
            report = import_roster(course, request.FILES["roster_file"], actor=request.user)
            for row_no, reg, reason in report.skipped[:10]:
                messages.warning(request, f"Row {row_no}: {reg} — {reason}")
            if len(report.skipped) > 10:
                messages.warning(request, f"…and {len(report.skipped) - 10} more skipped rows.")
            messages.success(request, report.summary())
            return redirect("courses:detail", course_id=course.id)
    else:
        form = RosterUploadForm()
    return render(request, "courses/roster_upload.html", {"course": course, "form": form})
