"""THE object-level permission helper every app calls (FR-02, deny-by-default)."""
from .models import Enrollment


def user_role_in_course(user, course):
    """Return 'admin' | 'lecturer' | 'ta' | 'student' | None (None = no access)."""
    if not getattr(user, "is_authenticated", False):
        return None
    if user.is_admin_role:
        return "admin"
    if course.lecturer_id == user.id:
        return "lecturer"
    try:
        enr = Enrollment.objects.get(course=course, user=user, is_active=True)
    except Enrollment.DoesNotExist:
        return None
    if enr.role_in_course == Enrollment.Role.LECTURER:
        return "lecturer"
    if enr.role_in_course == Enrollment.Role.TA:
        return "ta"
    return "student"


def is_staff_of(user, course):
    """Lecturer/TA/admin of this course — allowed to manage materials, roster, grades."""
    return user_role_in_course(user, course) in ("lecturer", "ta", "admin")
