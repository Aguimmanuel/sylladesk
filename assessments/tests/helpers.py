from datetime import timedelta

from django.utils import timezone

from accounts.tests.helpers import make_user
from courses.models import Enrollment
from courses.tests.helpers import make_course

from ..models import Question, Test


def make_test(course=None, *, open_in=1, close_in=8, n=2, **kwargs):
    lecturer = make_user(username="testlect@psb.lms", global_role="lecturer")
    course = course or make_course(lecturer=lecturer)
    defaults = dict(
        title="Week 4 Quiz", open_at=timezone.now() + timedelta(days=open_in),
        close_at=timezone.now() + timedelta(days=close_in),
        n_to_answer=n, created_by=course.lecturer,
    )
    defaults.update(kwargs)
    return Test.objects.create(course=course, **defaults)


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
