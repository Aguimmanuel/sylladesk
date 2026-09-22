from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from core.auditing import audit
from courses.access import is_staff_of
from courses.models import Course

from .forms import AnnouncementForm
from .models import Announcement


def _staff_course(request, course_id):
    course = get_object_or_404(Course, pk=course_id, is_active=True)
    if not is_staff_of(request.user, course):
        return course, False
    return course, True


@login_required
@require_POST
def create(request, course_id):
    course, allowed = _staff_course(request, course_id)
    if not allowed:
        return redirect("courses:detail", course_id=course.id)
    form = AnnouncementForm(request.POST)
    if form.is_valid():
        Announcement.objects.create(
            course=course, title=form.cleaned_data["title"].strip(),
            body=form.cleaned_data["body"], is_pinned=form.cleaned_data["is_pinned"],
            created_by=request.user,
        )
        audit(actor=request.user, action="announcement.create", obj=course)
        messages.success(request, "Announcement posted.")
    else:
        messages.error(request, form.errors.as_text())
    return redirect("courses:detail", course_id=course.id)


@login_required
def edit(request, course_id, announcement_id):
    course, allowed = _staff_course(request, course_id)
    if not allowed:
        return redirect("courses:detail", course_id=course.id)
    a = get_object_or_404(Announcement, pk=announcement_id, course=course, is_active=True)
    form = AnnouncementForm(request.POST or None,
                            initial={"title": a.title, "body": a.body,
                                     "is_pinned": a.is_pinned})
    if request.method == "POST" and form.is_valid():
        a.title = form.cleaned_data["title"].strip()
        a.body = form.cleaned_data["body"]
        a.is_pinned = form.cleaned_data["is_pinned"]
        a.save()
        audit(actor=request.user, action="announcement.update", obj=a)
        messages.success(request, "Announcement updated.")
        return redirect("courses:detail", course_id=course.id)
    return render(request, "announcements/edit.html", {
        "course": course, "announcement": a, "form": form,
    })


@login_required
@require_POST
def delete(request, course_id, announcement_id):
    course, allowed = _staff_course(request, course_id)
    if not allowed:
        return redirect("courses:detail", course_id=course.id)
    a = get_object_or_404(Announcement, pk=announcement_id, course=course, is_active=True)
    a.is_active = False
    a.save(update_fields=["is_active"])
    audit(actor=request.user, action="announcement.delete", obj=a)
    messages.success(request, "Announcement removed. You can bring it back from the Trash.")
    return redirect("courses:detail", course_id=course.id)
