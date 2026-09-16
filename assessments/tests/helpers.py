from django.utils import timezone

from accounts.tests.helpers import make_user
from courses.models import Enrollment
from courses.tests.helpers import make_course, make_lecturer

from ..models import Question, Test

_n = [0]


def make_test(course=None, *, n_obj=2, n_tf=0, n_short=0, **kwargs):
    if course is None:
        # unique lecturer and course code: tests build several tests per run
        _n[0] += 1
        lecturer = make_lecturer()
        course = make_course(lecturer=lecturer, code=f"PSB 41{_n[0]}")
    defaults = dict(
        title="Week 4 Quiz", n_objective=n_obj, n_tf=n_tf, n_subjective=n_short,
        created_by=course.lecturer,
    )
    defaults.update(kwargs)
    return Test.objects.create(course=course, **defaults)


def open_test(t):
    """Flip a draft straight to live, bypassing the pool check."""
    if not t.started_at:
        t.started_at = timezone.now()
        t.save(update_fields=["started_at"])
    return t


def add_mcq(t, *, text="Photosynthesis happens in the?", key="B", options="Mitochondria\nChloroplast\nNucleus"):
    return Question.objects.create(test=t, kind="mcq", text=text,
                                   options=options, answer_key=key, order=t.questions.count())


def add_tf(t, *, text="A virus is a living cell.", key="FALSE"):
    return Question.objects.create(test=t, kind="tf", text=text, answer_key=key, order=t.questions.count())


def add_short(t, *, text="Powerhouse of the cell?", accepted="Mitochondrion\nmitochondria"):
    return Question.objects.create(test=t, kind="short", text=text,
                                   accepted_answers=accepted, order=t.questions.count())


def make_student_enrolled(reg="MOUAU/PSB/26/070001"):
    s = make_user(username=reg, reg_no=reg, full_name="Quiz Taker")
    return s


def enroll(course, student):
    return Enrollment.objects.create(course=course, user=student, role_in_course="student")
