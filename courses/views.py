from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, transaction
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from core.auditing import audit

from .access import is_staff_of, user_role_in_course
from .forms import CourseForm, RosterUploadForm
from .models import Course, Enrollment, RosterEntry
from .services import claim_roster_entries, import_roster

User = get_user_model()


@login_required
def list_courses(request):
    user = request.user
    # Late claim: a roster uploaded after a student signed up still reaches
    # them on their next visit. Idempotent and race-safe on every list view.
    if user.global_role == User.GlobalRole.STUDENT and user.reg_no:
        with transaction.atomic():
            joined = claim_roster_entries(user)
        if joined:
            audit(actor=user, action="roster.claim_late", obj=user,
                  detail={"courses": [c.code for c in joined]})
            messages.success(request, f"You have been added to {len(joined)} new course(s).")
    if user.is_admin_role:
        # platform staff: every active course (they hold "admin" role in all of them)
        courses = Course.objects.filter(is_active=True).select_related("lecturer")
    elif user.is_lecturer_role:
        # courses they own OR co-lecture via an active lecturer enrollment
        courses = (
            Course.objects.filter(is_active=True, lecturer=user)
            | Course.objects.filter(
                is_active=True, enrollments__user=user,
                enrollments__is_active=True,
                enrollments__role_in_course=Enrollment.Role.LECTURER)
        ).distinct().select_related("lecturer")
    else:
        courses = Course.objects.filter(
            enrollments__user=user, enrollments__is_active=True, is_active=True
        ).distinct().select_related("lecturer")
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
    assignments = course.assignments.filter(is_active=True)
    roster = RosterEntry.objects.filter(course=course).select_related("claimed_by") if staff else None
    students = removed_students = None
    if staff:
        students = (Enrollment.objects.filter(course=course, role_in_course="student", is_active=True)
                    .select_related("user").order_by("user__full_name"))
        removed_students = (Enrollment.objects.filter(course=course, role_in_course="student", is_active=False)
                            .select_related("user").order_by("user__full_name"))
    return render(request, "courses/detail.html", {
        "course": course, "role": role, "materials": materials, "roster": roster,
        "assignments": assignments,
        "is_staff": staff, "mform": MaterialForm() if staff else None,
        "students": students, "removed_students": removed_students,
    })


@login_required
@require_POST
def enrollment_toggle(request, course_id, user_id, action):
    """Remove or restore a student's participation. Soft toggle: the row
    survives for audit and restore."""
    if action not in ("remove", "restore"):
        raise Http404()
    course = _course_or_404(course_id)
    if not is_staff_of(request.user, course):
        messages.error(request, "Only course staff can manage students.")
        return redirect("courses:detail", course_id=course.id)
    target = get_object_or_404(User, pk=user_id)
    try:
        enr = Enrollment.objects.get(course=course, user=target)
    except Enrollment.DoesNotExist:
        raise Http404()
    if enr.role_in_course != Enrollment.Role.STUDENT:
        messages.error(request, "Only student enrollments can be changed here.")
        return redirect("courses:detail", course_id=course.id)
    if action == "remove" and enr.is_active:
        enr.is_active = False
        enr.save(update_fields=["is_active"])
        audit(actor=request.user, action="enrollment.remove", obj=enr,
              detail={"student": target.username})
        messages.success(request, f"{target.full_name} removed from {course.code}. Restore here anytime.")
    elif action == "restore" and not enr.is_active:
        enr.is_active = True
        enr.save(update_fields=["is_active"])
        audit(actor=request.user, action="enrollment.restore", obj=enr,
              detail={"student": target.username})
        messages.success(request, f"{target.full_name} restored to {course.code}.")
    return redirect("courses:detail", course_id=course.id)


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
