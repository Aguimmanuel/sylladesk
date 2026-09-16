from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from ..models import Attempt
from ..services import start_attempt
from .helpers import (add_mcq, add_short, enroll, make_student_enrolled,
                      make_test)


class JoinViewTests(TestCase):
    def setUp(self):
        self.t = make_test(open_in=-1)
        self.s = make_student_enrolled()
        enroll(self.t.course, self.s)
        add_mcq(self.t)
        add_mcq(self.t, text="Water is?", key="A", options="H2O\nCO2")

    def test_open_state_shows_start_button(self):
        self.client.force_login(self.s)
        r = self.client.get(reverse("assessments:join", args=[self.t.join_code]))
        self.assertContains(r, "Start the test")

    def test_upcoming_shows_wait(self):
        self.t.open_at = timezone.now() + timedelta(days=1)
        self.t.save()
        self.client.force_login(self.s)
        r = self.client.get(reverse("assessments:join", args=[self.t.join_code]))
        self.assertContains(r, "has not opened yet")

    def test_released_shows_score_and_nonparticipant_message(self):
        a = start_attempt(self.t, student=self.s)
        a.submitted_at = timezone.now()
        a.save()
        self.t.results_released_at = timezone.now()
        self.t.save()
        self.client.force_login(self.s)
        r = self.client.get(reverse("assessments:join", args=[self.t.join_code]))
        self.assertContains(r, "Your score")
        other = make_student_enrolled(reg="MOUAU/PSB/26/070008")
        enroll(self.t.course, other)
        self.client.force_login(other)
        r = self.client.get(reverse("assessments:join", args=[self.t.join_code]))
        self.assertContains(r, "you did not participate")

    def test_take_page_renders_drawn_questions_and_countdown(self):
        self.client.force_login(self.s)
        r = self.client.get(reverse("assessments:take", args=[self.t.join_code]))
        self.assertEqual(Attempt.objects.filter(test=self.t, student=self.s).count(), 1)
        self.assertContains(r, "countdown")
        self.assertContains(r, "Photosynthesis")

    def test_bad_code_is_404(self):
        self.client.force_login(self.s)
        r = self.client.get(reverse("assessments:join", args=["ZZZZZZ"]))
        self.assertEqual(r.status_code, 404)
