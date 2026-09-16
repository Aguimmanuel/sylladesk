from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import F
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from core.auditing import audit
from core.storage import get_storage

from courses.access import user_role_in_course
from courses.models import Course
from courses.views import _course_or_404

from .forms import MaterialEditForm, MaterialForm
from .models import Material
from .services import create_material


def _material_or_404(course_id, material_id):
    return get_object_or_404(
        Material, pk=material_id, course_id=course_id, is_deleted=False
    )


@login_required
@require_POST
def upload(request, course_id):
    course = _course_or_404(course_id)
    if user_role_in_course(request.user, course) not in ("lecturer", "ta", "admin"):
        messages.error(request, "Only the lecturer can upload materials.")
        return redirect("courses:detail", course_id=course.id)
    form = MaterialForm(request.POST, request.FILES)
    if not form.is_valid():
        for errs in form.errors.values():
            for e in errs:
                messages.error(request, e)
        return redirect("courses:detail", course_id=course.id)
    result = create_material(
        course=course,
        title=form.cleaned_data["title"],
        week_no=form.cleaned_data["week_no"],
        uploaded=request.FILES["material_file"],
        actor=request.user,
    )
    if not result.ok:
        messages.error(request, result.error)
        return redirect("courses:detail", course_id=course.id)
    messages.success(request, f"Uploaded “{result.material.title}”.")
    return redirect("courses:detail", course_id=course.id)


def _open_material(request, course_id, material_id):
    """Shared gate for view/download: enrolled (any role) or 404."""
    course = _course_or_404(course_id)
    if user_role_in_course(request.user, course) is None:
        raise Http404()
    material = _material_or_404(course_id, material_id)
    return material, get_storage().open(material.file)


@login_required
def view_file(request, course_id, material_id):
    """Open in the browser; does not count as a download."""
    material, fh = _open_material(request, course_id, material_id)
    return FileResponse(fh, filename=material.file.original_name)


@login_required
def download(request, course_id, material_id):
    material, fh = _open_material(request, course_id, material_id)
    Material.objects.filter(pk=material.pk).update(download_count=F("download_count") + 1)
    return FileResponse(fh, as_attachment=True, filename=material.file.original_name)


@login_required
def edit(request, course_id, material_id):
    course = _course_or_404(course_id)
    material = _material_or_404(course_id, material_id)
    if user_role_in_course(request.user, course) not in ("lecturer", "ta", "admin"):
        messages.error(request, "Only the lecturer can edit materials.")
        return redirect("courses:detail", course_id=course.id)
    form = MaterialEditForm(request.POST or None, instance=material)
    if request.method == "POST" and form.is_valid():
        form.save()
        audit(actor=request.user, action="material.update", obj=material)
        messages.success(request, "Material updated.")
        return redirect("courses:detail", course_id=course.id)
    return render(request, "materials/edit.html",
                  {"course": course, "material": material, "form": form})


@login_required
@require_POST
def delete(request, course_id, material_id):
    course = _course_or_404(course_id)
    if user_role_in_course(request.user, course) not in ("lecturer", "ta", "admin"):
        messages.error(request, "Only the lecturer can delete materials.")
        return redirect("courses:detail", course_id=course.id)
    material = _material_or_404(course_id, material_id)
    material.is_deleted = True
    material.save(update_fields=["is_deleted"])
    audit(actor=request.user, action="material.delete", obj=material)
    messages.success(request, f"Removed “{material.title}”.")
    return redirect("courses:detail", course_id=course.id)
