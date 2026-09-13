from accounts.tests.helpers import make_user
from courses.models import Course

_n = [0]


def make_lecturer(username=None):
    """Unique lecturer usernames — tests create several per test run."""
    if username is None:
        _n[0] += 1
        username = f"lect{_n[0]}@psb.lms"
    return make_user(username=username, full_name="Test Lecturer",
                     global_role="lecturer")


def make_course(lecturer=None, code="PSB 413", session="2025/2026"):
    lecturer = lecturer or make_lecturer()
    return Course.objects.create(
        code=code,
        title="Cytogenetics Of Plants",
        session=session,
        semester="first",
        lecturer=lecturer,
    )
