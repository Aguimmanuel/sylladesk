from django.test import TestCase
from django.utils import timezone
from django.urls import reverse

from ..models import Attempt, Test, TestUnlock
from ..services import (advance_section, release_results, save_answer,
                        start_attempt, submit)
from .helpers import (add_mcq, add_short, enroll, make_student_enrolled,
                      make_test, open_test)


class JoinViewTests(TestCase):
    def setUp(self):
        self.t = make_test(n_obj=2)
        open_test(self.t)
        self.s = make_student_enrolled()
        enroll(self.t.course, self.s)
        add_mcq(self.t)
        add_mcq(self.t, text="Water is?", key="A", options="H2O\nCO2")

    def test_open_state_shows_start_button(self):
        self.client.force_login(self.s)
        r = self.client.get(reverse("assessments:join", args=[self.t.join_code]))
        self.assertContains(r, "Start the test")

    def test_draft_shows_waiting_for_lecturer(self):
        draft = make_test(n_obj=1)
        add_mcq(draft)
        enroll(draft.course, self.s)
        self.client.force_login(self.s)
        r = self.client.get(reverse("assessments:join", args=[draft.join_code]))
        self.assertContains(r, "has not started yet")

    def test_closed_shows_closed(self):
        start_attempt(self.t, student=self.s)
        self.t.closed_at = timezone.now()
        self.t.save()
        self.client.force_login(self.s)
        r = self.client.get(reverse("assessments:join", args=[self.t.join_code]))
        self.assertContains(r, "Your test is running")  # running attempt outlives close

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
        self.client.post(reverse("assessments:enter", args=[self.t.course_id, self.t.id]),
                         {"code": self.t.join_code})  # the code front door
        r = self.client.get(reverse("assessments:take", args=[self.t.join_code]))
        self.assertEqual(Attempt.objects.filter(test=self.t, student=self.s).count(), 1)
        self.assertContains(r, "countdown")
        self.assertContains(r, "Photosynthesis")

    def test_bad_code_is_404(self):
        self.client.force_login(self.s)
        r = self.client.get(reverse("assessments:join", args=["ZZZZZZ"]))
        self.assertEqual(r.status_code, 404)

    def test_join_page_embeds_correct_status_url(self):
        """Regression: the poll used to derive its URL from the address bar
        and dropped the join code, so the live flip never fired."""
        self.client.force_login(self.s)
        r = self.client.get(reverse("assessments:join", args=[self.t.join_code]))
        self.assertContains(r, reverse("assessments:status", args=[self.t.join_code]))


class RunViewTests(TestCase):
    """Start / close / advance / edit through the real routes."""

    def setUp(self):
        self.t = make_test(n_obj=1, n_short=1)
        add_mcq(self.t)
        add_short(self.t)
        self.s = make_student_enrolled()
        enroll(self.t.course, self.s)

    def test_start_via_view_then_student_can_take(self):
        self.client.force_login(self.t.created_by)
        r = self.client.post(reverse("assessments:start", args=[self.t.course_id, self.t.id]),
                             follow=True)
        self.assertContains(r, "The test has started")
        self.t.refresh_from_db()
        self.assertIsNotNone(self.t.started_at)
        self.client.force_login(self.s)
        r = self.client.get(reverse("assessments:join", args=[self.t.join_code]))
        self.assertContains(r, "Start the test")

    def test_close_via_view_stops_new_joiner(self):
        open_test(self.t)
        self.client.force_login(self.t.created_by)
        r = self.client.post(reverse("assessments:close", args=[self.t.course_id, self.t.id]),
                             follow=True)
        self.assertContains(r, "The test is closed")
        late = make_student_enrolled(reg="MOUAU/PSB/26/070003")
        enroll(self.t.course, late)
        self.client.force_login(late)
        r = self.client.get(reverse("assessments:join", args=[self.t.join_code]))
        self.assertContains(r, "The test is closed")

    def test_advance_via_view_moves_to_next_section(self):
        open_test(self.t)
        a = start_attempt(self.t, student=self.s)
        self.client.force_login(self.s)
        TestUnlock.objects.create(test=self.t, student=self.s)  # code already typed
        r = self.client.post(reverse("assessments:advance", args=[self.t.join_code]), follow=True)
        a.refresh_from_db()
        self.assertEqual(a.current_section, "subjective")
        self.assertContains(r, "Section 2 of 2")

    def test_edit_via_view_saves_settings(self):
        self.client.force_login(self.t.created_by)
        url = reverse("assessments:edit", args=[self.t.course_id, self.t.id])
        r = self.client.get(url)
        self.assertContains(r, "Edit test settings")
        r = self.client.post(url, {
            "title": "Renamed Quiz",
            "n_objective": "1", "n_tf": "0", "n_subjective": "1",
            "seconds_objective": "20", "seconds_tf": "20", "seconds_subjective": "90",
            "points_per_question": "2", "allow_review": "on",
        }, follow=True)
        self.assertContains(r, "Settings saved")
        self.t.refresh_from_db()
        self.assertEqual(self.t.title, "Renamed Quiz")
        self.assertEqual(self.t.seconds_subjective, 90)
        self.assertEqual(self.t.points_per_question, 2)

    def test_edit_locked_after_start(self):
        open_test(self.t)
        self.client.force_login(self.t.created_by)
        r = self.client.get(reverse("assessments:edit", args=[self.t.course_id, self.t.id]),
                            follow=True)
        self.assertContains(r, "Settings are locked once the test has started")


class AddQuestionViewTests(TestCase):
    def test_add_mcq_question_via_form(self):
        """Owner hit a 500 posting Q1 exactly like this on the live site."""
        t = make_test(n_obj=1)
        lect = t.created_by
        self.client.force_login(lect)
        r = self.client.post(reverse("assessments:add_question", args=[t.course_id, t.id]), {
            "kind": "mcq",
            "text": "What is the output of print(2 + 3 * 4)?",
            "options": "20\n14\n24\n10",
            "answer_key": "B",
            "accepted_answers": "",
        }, follow=True)
        self.assertContains(r, "Question added.")
        self.assertEqual(t.questions.count(), 1)

    def test_detail_page_renders_for_staff(self):
        t = make_test(n_obj=1)
        self.client.force_login(t.created_by)
        r = self.client.get(reverse("assessments:detail", args=[t.course_id, t.id]))
        self.assertContains(r, "Add a question")
        self.assertContains(r, "Start test")

    def test_delete_question_via_form(self):
        t = make_test(n_obj=1)  # pool floor is 1; two questions means one is removable
        add_mcq(t)
        add_mcq(t, text="Spare", key="A", options="x\ny")
        self.client.force_login(t.created_by)
        q = t.questions.first()
        r = self.client.post(reverse("assessments:delete_question",
                                     args=[t.course_id, t.id, q.id]), follow=True)
        self.assertContains(r, "removed")
        self.assertEqual(t.questions.count(), 1)


class LiveStatusViewTests(TestCase):
    def test_status_flips_upcoming_to_open_without_refresh(self):
        t = make_test(n_obj=1)
        add_mcq(t)
        s = make_student_enrolled()
        enroll(t.course, s)
        self.client.force_login(s)
        url = reverse("assessments:status", args=[t.join_code])
        r = self.client.get(url)
        self.assertEqual(r.json()["state"], "upcoming")
        open_test(t)
        r = self.client.get(url)
        self.assertEqual(r.json()["state"], "open")


class ReviewViewTests(TestCase):
    def _test_with_one_submitted_attempt(self):
        t = make_test(n_obj=1, n_short=1)
        add_mcq(t)
        add_short(t, accepted="Chlorophyll")
        s = make_student_enrolled()
        enroll(t.course, s)
        open_test(t)
        a = start_attempt(t, student=s)
        mcq = a.drawn_questions()[0]
        save_answer(a, question_id=mcq.id, choice="B")  # correct
        advance_section(a)
        short = a.drawn_questions()[-1]
        save_answer(a, question_id=short.id, text="chloroplast")  # wrong on purpose
        submit(a)
        return t, s, a

    def test_lecturer_sees_per_student_verdicts(self):
        t, s, a = self._test_with_one_submitted_attempt()
        self.client.force_login(t.created_by)
        r = self.client.get(reverse("assessments:attempt", args=[t.course_id, t.id, a.id]))
        self.assertContains(r, s.full_name)
        self.assertContains(r, "Correct")
        self.assertContains(r, "Wrong")
        self.assertContains(r, "chloroplast")

    def test_student_sees_own_review_after_release(self):
        t, s, a = self._test_with_one_submitted_attempt()
        release_results(t, actor=t.created_by)
        self.client.force_login(s)
        r = self.client.get(reverse("assessments:join", args=[t.join_code]))
        self.assertContains(r, "Your answers")
        self.assertContains(r, "Your answer")
        self.assertContains(r, "Correct answer")
        self.assertContains(r, "chloroplast")

    def test_clone_via_view_creates_fresh_draft(self):
        t, s, a = self._test_with_one_submitted_attempt()
        self.client.force_login(t.created_by)
        r = self.client.post(reverse("assessments:clone", args=[t.course_id, t.id]), follow=True)
        self.assertContains(r, "Cloned")
        self.assertEqual(Test.objects.filter(course=t.course).count(), 2)
        copy = Test.objects.get(title__endswith="(copy)")
        self.assertEqual(copy.status, "draft")
        self.assertEqual(copy.questions.count(), t.questions.count())


class LiveAttemptsTests(TestCase):
    def test_attempts_fragment_shows_new_attempts(self):
        t = make_test(n_obj=1)
        add_mcq(t)
        s = make_student_enrolled()
        enroll(t.course, s)
        open_test(t)
        url = reverse("assessments:attempts_fragment", args=[t.course_id, t.id])
        self.client.force_login(t.created_by)
        r = self.client.get(url)
        self.assertContains(r, "No student has started yet.")
        start_attempt(t, student=s)
        r = self.client.get(url)
        self.assertContains(r, s.full_name)
        self.assertContains(r, "In progress")

    def test_attempts_fragment_is_staff_only(self):
        t = make_test(n_obj=1)
        add_mcq(t)
        s = make_student_enrolled()
        enroll(t.course, s)
        self.client.force_login(s)
        r = self.client.get(reverse("assessments:attempts_fragment", args=[t.course_id, t.id]))
        self.assertEqual(r.status_code, 302)


class StudentTestListTests(TestCase):
    def test_student_sees_upcoming_not_draft_and_view_link(self):
        t = make_test(n_obj=1)
        add_mcq(t)
        s = make_student_enrolled()
        enroll(t.course, s)
        self.client.force_login(s)
        r = self.client.get(reverse("courses:detail", args=[t.course_id]))
        self.assertContains(r, "Upcoming")
        self.assertNotContains(r, "Draft")
        open_test(t)
        r = self.client.get(reverse("courses:detail", args=[t.course_id]))
        self.assertContains(r, "View")

    def test_join_page_has_back_link_to_course(self):
        t = make_test(n_obj=1)
        add_mcq(t)
        s = make_student_enrolled()
        enroll(t.course, s)
        open_test(t)
        self.client.force_login(s)
        r = self.client.get(reverse("assessments:join", args=[t.join_code]))
        self.assertContains(r, "courses/%d" % t.course_id)


class ReopenViewTests(TestCase):
    def test_close_then_reopen_via_view(self):
        t = make_test(n_obj=1)
        add_mcq(t)
        open_test(t)
        self.client.force_login(t.created_by)
        self.client.post(reverse("assessments:close", args=[t.course_id, t.id]))
        r = self.client.post(reverse("assessments:reopen", args=[t.course_id, t.id]), follow=True)
        self.assertContains(r, "open again")
        t.refresh_from_db()
        self.assertIsNone(t.closed_at)
        self.assertContains(r, "Close test")  # back to the Running card


class ArchiveViewTests(TestCase):
    def test_remove_hides_from_everyone_and_restore_brings_back(self):
        t = make_test(n_obj=1)
        add_mcq(t)
        s = make_student_enrolled()
        enroll(t.course, s)
        self.client.force_login(t.created_by)
        self.client.post(reverse("assessments:archive", args=[t.course_id, t.id]))
        self.client.force_login(s)
        r = self.client.get(reverse("courses:detail", args=[t.course_id]))
        self.assertNotContains(r, t.title)  # gone from the student's course page
        r = self.client.get(reverse("assessments:join", args=[t.join_code]))
        self.assertEqual(r.status_code, 404)  # join by code is dead too
        self.client.force_login(t.created_by)
        r = self.client.get(reverse("courses:detail", args=[t.course_id]))
        self.assertContains(r, "Trash (1)")  # the course page shows the bin
        r = self.client.post(reverse("courses:trash_restore",
                                     args=[t.course_id, "test", t.id]), follow=True)
        self.assertEqual(r.status_code, 200)  # regression: restore used to 404
        r = self.client.get(reverse("courses:detail", args=[t.course_id]))
        self.assertContains(r, t.title)  # back in the live table
        self.assertNotContains(r, "Trash (1)")  # nothing left in the bin


class MakeupViewTests(TestCase):
    def test_set_list_via_view_and_students_blocked_or_allowed(self):
        t = make_test(n_obj=1, is_makeup=True)
        add_mcq(t)
        on_list = make_student_enrolled()
        off_list = make_student_enrolled(reg="MOUAU/PSB/26/070002")
        enroll(t.course, on_list)
        enroll(t.course, off_list)
        self.client.force_login(t.created_by)
        r = self.client.post(reverse("assessments:set_students", args=[t.course_id, t.id]),
                             {"students": [str(on_list.id)]}, follow=True)
        self.assertContains(r, "Makeup list saved")
        self.assertContains(r, on_list.full_name)  # the picker shows the saved list
        open_test(t)  # list saved while drafting, then the test goes live
        self.client.force_login(off_list)
        r = self.client.get(reverse("assessments:join", args=[t.join_code]))
        self.assertContains(r, "not on the list")
        r = self.client.get(reverse("assessments:take", args=[t.join_code]), follow=True)
        self.assertContains(r, "not on the list")  # refused at start too
        self.client.force_login(on_list)
        r = self.client.get(reverse("assessments:join", args=[t.join_code]))
        self.assertContains(r, "Start the test")

    def test_makeup_test_tagged_on_course_page(self):
        t = make_test(n_obj=1, is_makeup=True)
        add_mcq(t)
        self.client.force_login(t.created_by)
        r = self.client.get(reverse("courses:detail", args=[t.course_id]))
        self.assertContains(r, "Makeup")


class CodeFrontDoorTests(TestCase):
    """The join code gates starting: no typed code, no test."""

    def _ready(self):
        t = make_test(n_obj=1)
        add_mcq(t)
        s = make_student_enrolled()
        enroll(t.course, s)
        open_test(t)
        return t, s

    def test_view_button_leads_to_code_entry_then_test_opens(self):
        t, s = self._ready()
        self.client.force_login(s)
        # course page: the View button points at the code door, not the test
        r = self.client.get(reverse("courses:detail", args=[t.course_id]))
        self.assertContains(r, reverse("assessments:enter", args=[t.course_id, t.id]))
        # wrong code refused
        r = self.client.post(reverse("assessments:enter", args=[t.course_id, t.id]),
                             {"code": "XXXXXX"})
        self.assertContains(r, "does not match")
        # right code opens the door for keeps
        r = self.client.post(reverse("assessments:enter", args=[t.course_id, t.id]),
                             {"code": t.join_code})
        self.assertEqual(r.status_code, 302)
        r = self.client.get(reverse("assessments:join", args=[t.join_code]))
        self.assertContains(r, "Start the test")
        # after unlocking, the course page View goes straight to the test
        r = self.client.get(reverse("courses:detail", args=[t.course_id]))
        self.assertContains(r, reverse("assessments:join", args=[t.join_code]))

    def test_take_without_code_is_turned_away(self):
        t, s = self._ready()
        self.client.force_login(s)
        r = self.client.get(reverse("assessments:take", args=[t.join_code]), follow=True)
        self.assertContains(r, "type the code")
        self.assertEqual(
            __import__("assessments.models", fromlist=["TestUnlock"])
            .TestUnlock.objects.count(), 0)

    def test_typed_join_code_unlocks_on_arrival(self):
        t, s = self._ready()
        self.client.force_login(s)
        self.client.post(reverse("assessments:join_box"), {"code": t.join_code})
        r = self.client.get(reverse("assessments:join", args=[t.join_code]))
        self.assertContains(r, "Start the test")
        r = self.client.get(reverse("assessments:take", args=[t.join_code]))
        self.assertEqual(r.status_code, 200)

    def test_released_tests_need_no_code_to_view_scores(self):
        t, s = self._ready()
        a = start_attempt(t, student=s)
        a.submitted_at = timezone.now()
        a.save()
        release_results(t, actor=t.created_by)
        self.client.force_login(s)
        r = self.client.get(reverse("courses:detail", args=[t.course_id]))
        self.assertContains(r, reverse("assessments:join", args=[t.join_code]))

    def test_course_page_hides_code_column_from_staff(self):
        t, s = self._ready()
        self.client.force_login(t.created_by)
        r = self.client.get(reverse("courses:detail", args=[t.course_id]))
        self.assertNotContains(r, "<strong>" + t.join_code + "</strong>")
