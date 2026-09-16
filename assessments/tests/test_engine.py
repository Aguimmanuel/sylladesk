from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import AuditLog

from ..models import Answer, Attempt, Question
from ..services import (add_question, create_test, finalize, join_state,
                        regenerate_join_code, release_results, save_answer,
                        start_attempt, submit)
from .helpers import (add_mcq, add_short, add_tf, enroll, make_student_enrolled,
                      make_test)


class CreationTests(TestCase):
    def test_create_generates_unambiguous_code(self):
        t = make_test()
        self.assertEqual(len(t.join_code), 6)
        allowed = set("ABCDEFGHJKMNPQRSTUVWXYZ23456789")
        self.assertTrue(set(t.join_code) <= allowed)

    def test_close_before_open_rejected(self):
        with self.assertRaises(ValueError):
            create_test(None, actor=None, title="x",
                        open_at=timezone.now() + timedelta(days=2),
                        close_at=timezone.now() + timedelta(days=1), n_to_answer=1)

    def test_question_validation(self):
        t = make_test()
        with self.assertRaises(ValueError):
            add_question(t, actor=None, kind="mcq", text="q", options="only one", answer_key="A")
        with self.assertRaises(ValueError):
            add_question(t, actor=None, kind="mcq", text="q",
                         options="a\nb\nc", answer_key="D")
        with self.assertRaises(ValueError):
            add_question(t, actor=None, kind="tf", text="q", answer_key="MAYBE")
        with self.assertRaises(ValueError):
            add_question(t, actor=None, kind="short", text="q", accepted_answers="")
        q = add_question(t, actor=None, kind="short", text="q",
                         accepted_answers="X  \n\nY")
        self.assertEqual(q.key_variants(), ["x", "y"])  # normalized at save path


class JoinLifecycleTests(TestCase):
    def setUp(self):
        self.t = make_test()
        self.s = make_student_enrolled()
        enroll(self.t.course, self.s)
        for _ in range(3):
            add_mcq(self.t)

    def test_five_states(self):
        self.assertEqual(join_state(self.t, student=self.s)[0], "upcoming")
        self.t.open_at = timezone.now() - timedelta(minutes=1)
        self.t.save()
        self.assertEqual(join_state(self.t, student=self.s)[0], "open")
        a = start_attempt(self.t, student=self.s)
        self.assertEqual(join_state(self.t, student=self.s)[0], "in_progress")
        a.expires_at = timezone.now() - timedelta(seconds=30)
        a.save()
        finalize(a)
        self.assertEqual(join_state(self.t, student=self.s)[0], "submitted")
        self.t.close_at = timezone.now() - timedelta(seconds=1)
        self.t.save()
        self.t.refresh_from_db()
        state, a2 = join_state(self.t, student=self.s)
        self.assertEqual(state, "submitted")  # has an attempt, finalized

    def test_start_draws_n_fixed_and_times(self):
        self.t.open_at = timezone.now() - timedelta(minutes=1)
        self.t.save()
        a = start_attempt(self.t, student=self.s)
        self.assertEqual(len(a.drawn_questions()), 2)  # N of M=3
        again = start_attempt(self.t, student=self.s)
        self.assertEqual(again.id, a.id)  # retry-safe: same attempt
        expected = self.t.seconds_objective * 2
        self.assertEqual(a.duration_seconds(), expected)
        self.assertEqual(round((a.expires_at - a.started_at).total_seconds()), expected)

    def test_short_answer_gets_60s(self):
        self.t.open_at = timezone.now() - timedelta(minutes=1)
        self.t.save()
        self.t.questions.all().delete()
        add_short(self.t)
        add_short(self.t, text="Another?", accepted="x")
        a = start_attempt(self.t, student=self.s)
        self.assertEqual(a.duration_seconds(), 120)

    def test_non_enrolled_cannot_start(self):
        self.t.open_at = timezone.now() - timedelta(minutes=1)
        self.t.save()
        outsider = make_student_enrolled(reg="MOUAU/PSB/26/070009")
        with self.assertRaises(ValueError):
            start_attempt(self.t, student=outsider)


class AnsweringTests(TestCase):
    def setUp(self):
        self.t = make_test()
        self.t.open_at = timezone.now() - timedelta(minutes=1)
        self.t.save()
        self.s = make_student_enrolled()
        enroll(self.t.course, self.s)
        self.qs = [add_mcq(self.t), add_mcq(self.t, text="Water is?", key="A",
                   options="H2O\nCO2")]
        self.a = start_attempt(self.t, student=self.s)

    def test_autosave_upsert_is_idempotent(self):
        save_answer(self.a, question_id=self.qs[0].id, choice="B")
        save_answer(self.a, question_id=self.qs[0].id, choice="B")
        self.assertEqual(Answer.objects.filter(attempt=self.a).count(), 1)

    def test_answer_to_undrawn_question_refused(self):
        add_mcq(self.t, text="Not in your draw", key="A", options="x\ny")
        rogue = Question.objects.get(text="Not in your draw")
        with self.assertRaises(ValueError):
            save_answer(self.a, question_id=rogue.id, choice="A")

    def test_grading_objective_and_subjective(self):
        self.t.questions.all().delete()
        mcq = add_mcq(self.t)
        short = add_short(self.t, accepted="Chlorophyll")
        self.a.drawn_ids = f"{mcq.id},{short.id}"
        self.a.save()
        self.a.expires_at = timezone.now() + timedelta(minutes=5)
        self.a.save()
        save_answer(self.a, question_id=mcq.id, choice="B")     # correct
        save_answer(self.a, question_id=short.id, text="  chlorophyll.  ")  # messy but matches
        self.assertEqual(self.a.score(), 2)
        save_answer(self.a, question_id=short.id, text="chloroplast")
        self.assertEqual(self.a.score(), 1)  # wrong variant, no point

    def test_submit_then_frozen(self):
        save_answer(self.a, question_id=self.qs[0].id, choice="B")
        submit(self.a)
        with self.assertRaises(ValueError):
            save_answer(self.a, question_id=self.qs[1].id, choice="A")

    def test_late_submit_refused_but_finalize_seals(self):
        save_answer(self.a, question_id=self.qs[0].id, choice="B")  # answered in time
        self.a.expires_at = timezone.now() - timedelta(minutes=2)
        self.a.save()
        with self.assertRaises(ValueError):
            submit(self.a)
        finalize(self.a)
        self.a.refresh_from_db()
        self.assertIsNotNone(self.a.submitted_at)  # auto-submitted at expiry
        with self.assertRaises(ValueError):
            save_answer(self.a, question_id=self.qs[1].id, choice="A")


class ReleaseTests(TestCase):
    def setUp(self):
        self.t = make_test(open_in=-1)
        self.s = make_student_enrolled()
        enroll(self.t.course, self.s)
        self.mcq = add_mcq(self.t)
        self.short = add_short(self.t, accepted="Chlorophyll")
        self.a = start_attempt(self.t, student=self.s)
        save_answer(self.a, question_id=self.mcq.id, choice="B")
        save_answer(self.a, question_id=self.short.id, text="Chlorophyll")
        submit(self.a)

    def test_release_closes_and_scores_visible(self):
        release_results(self.t, actor=self.t.created_by)
        self.t.refresh_from_db()
        self.assertIsNotNone(self.t.results_released_at)
        state, attempt = join_state(self.t, student=self.s)
        self.assertEqual(state, "released")
        self.assertEqual(attempt.score(), 2)
        self.assertTrue(AuditLog.objects.filter(action="test.release").exists())

    def test_release_finalizes_running_attempts(self):
        self.s2 = make_student_enrolled(reg="MOUAU/PSB/26/070002")
        enroll(self.t.course, self.s2)
        running = start_attempt(self.t, student=self.s2)
        release_results(self.t, actor=self.t.created_by)
        running.refresh_from_db()
        self.assertIsNotNone(running.submitted_at)


class CodeTests(TestCase):
    def test_regen_changes_code_and_audits(self):
        t = make_test()
        old = t.join_code
        regenerate_join_code(t, actor=t.created_by)
        self.assertNotEqual(t.join_code, old)
        self.assertTrue(AuditLog.objects.filter(action="test.regen_code").exists())
