"""Upload validation: extension whitelist + pure-python magic-byte check.

python-magic needs the libmagic C library, which the Render native runtime
doesn't guarantee — so V1 sniffs known signatures directly. Same protection,
zero system dependencies.
"""
from dataclasses import dataclass

from django.conf import settings

from core.auditing import audit
from core.storage import get_storage

EXT_MIME = {
    ".pdf": "application/pdf",
    ".ppt": "application/vnd.ms-powerpoint",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".doc": "application/msword",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}
# first bytes → formats: %PDF- (pdf), PK\x03\x04 (docx/pptx zips), OLE2 (doc/ppt)
_MAGIC = {
    b"%PDF-": "pdf",
    b"PK\x03\x04": "zip",
    b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1": "ole2",
}
_EXT_FAMILY = {".pdf": "pdf", ".pptx": "zip", ".docx": "zip", ".ppt": "ole2", ".doc": "ole2"}


@dataclass
class UploadResult:
    ok: bool
    material: object = None  # Material instance on success
    error: str = ""


def validate_upload(fileobj) -> tuple[bool, str]:
    ext = "." + fileobj.name.rsplit(".", 1)[-1].lower() if "." in fileobj.name else ""
    if ext not in EXT_MIME:
        return False, f"File type '{ext or '?'}' not allowed. Allowed: PDF, PPT, PPTX, DOC, DOCX."
    cap = settings.MATERIAL_MAX_MB * 1024 * 1024
    if getattr(fileobj, "size", 0) > cap:
        return False, f"File is larger than {settings.MATERIAL_MAX_MB} MB."
    head = fileobj.read(8)
    fileobj.seek(0)
    family = None
    for sig, fam in _MAGIC.items():
        if head.startswith(sig):
            family = fam
            break
    if family is None:
        return False, "File content doesn't look like a document (failed safety check)."
    if _EXT_FAMILY[ext] != family:
        return False, "File extension doesn't match its actual content (renamed file?)."
    return True, ""


def create_material(*, course, title, week_no, uploaded, actor):
    ok, error = validate_upload(uploaded)
    if not ok:
        return UploadResult(ok=False, error=error)
    f = get_storage().save(uploaded, course_id=course.id, kind="material", uploaded_by=actor)
    from .models import Material
    material = Material.objects.create(
        course=course, title=title, week_no=week_no, file=f, uploaded_by=actor,
    )
    audit(actor=actor, action="material.create", obj=material,
          detail={"size": f.size_bytes, "sha256": f.sha256})
    return UploadResult(ok=True, material=material)
