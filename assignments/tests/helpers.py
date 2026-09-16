import io

from django.utils import timezone

from accounts.tests.helpers import make_user
from courses.models import Enrollment
from courses.tests.helpers import make_course

from ..models import Assignment

PDF_BYTES = b"%PDF-1.4\nminimal test document\n%%EOF\n"
DOCX_BYTES = b"PK\x03\x04fake zip for docx tests\n"


def make_student(reg="MOUAU/PSB/26/060001"):
    s = make_user(username=reg, reg_no=reg, full_name="Test Student")
    return s


def enroll(course, student):
    return Enrollment.objects.create(course=course, user=student, role_in_course="student")


def make_assignment(course=None, *, due=None, allowed_ext=None):
    lecturer = make_user(username="asglect@psb.lms", global_role="lecturer")
    course = course or make_course(lecturer=lecturer)
    return Assignment.objects.create(
        course=course, title="Cell Division Report", instructions="Draw and label.",
        max_score=30, due_at=due or (timezone.now() + timezone.timedelta(days=3)),
        allowed_ext=allowed_ext or "pdf", created_by=course.lecturer,
    )


def upload(name="report.pdf", content=PDF_BYTES, ctype="application/pdf"):
    from django.core.files.uploadedfile import SimpleUploadedFile
    return SimpleUploadedFile(name, content, content_type=ctype)
