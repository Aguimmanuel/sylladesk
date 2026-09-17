from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from core.models import AuditLog

from ..models import Answer, Attempt, Question
from ..services import (add_question, advance_section, clone_test, close_test,
                        create_test, delete_question, finalize, join_state,
                        regenerate_join_code, release_results, save_answer,
                        start_attempt, start_test, submit, update_settings)
from .helpers import (add_mcq, add_short, add_tf, enroll, make_student_enrolled,
                      make_test, open_test)


class CreationTests(TestCase):
    def test_create_generates_unambiguous_code(self):
        t = make_test()
        self.assertEqual(len(t.join_code), 6)
        allowed = set("ABCDEFGHJKMNPQRSTUVWXYZ23456789")
        self.assertTrue(set(t.join_code) <= allowed)

    def test_zero_draws_rejected(self):
        with self.assertRaises(ValueError):
            create_test(None, actor=None, title="x", n_objective=0, n_tf=0, n_subjective=0)

    def test_seconds_bounds_enforced(self):
        with self.assertRaises(ValueError):
            create_test(None, actor=None, title="x", n_objective=1, seconds_objective=2)
        with self.assertRaises(ValueError):
            create_test(None, actor=None, title="x", n_objective=1, seconds_tf=9999)

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


class StartCloseTests(TestCase):
    def setUp(self):
        self.t = make_test(n_obj=2, n_tf=1, n_short=1)
        self.lecturer = self.t.created_by
        for _ in range(3):
            add_mcq(self.t)
        add_tf(self.t)
        add_short(self.t)

    def test_start_requires_pool_per_section(self):
        self.t.n_tf = 2  # pool has 1
        self.t.save()
        with self.assertRaises(ValueError):
            start_test(self.t, actor=self.lecturer)
        self.t.n_tf = 1
        self.t.save()
        start_test(self.t, actor=self.lecturer)
        self.t.refresh_from_db()
        self.assertIsNotNone(self.t.started_at)

    def test_start_is_one_way(self):
        start_test(self.t, actor=self.lecturer)
        with self.assertRaises(ValueError):
            start_test(self.t, actor=self.lecturer)
        self.assertTrue(AuditLog.objects.filter(action="test.open").exists())

    def test_close_stops_new_joins_running_finishes(self):
        s = make_student_enrolled()
        enroll(self.t.course, s)
        start_test(self.t, actor=self.lecturer)
        running = start_attempt(self.t, student=s)
        close_test(self.t, actor=self.lecturer)
        late = make_student_enrolled(reg="MOUAU/PSB/26/070002")
        enroll(self.t.course, late)
        state, _ = join_state(self.t, student=late)
        self.assertEqual(state, "closed")
        with self.assertRaises(ValueError):
            start_attempt(self.t, student=late)
        state_running, _ = join_state(self.t, student=s)
        self.assertEqual(state_running, "in_progress")  # own timer still rules
        q = running.drawn_questions()[0]
        save_answer(running, question_id=q.id, choice="B")  # still accepted
        self.assertTrue(AuditLog.objects.filter(action="test.close").exists())

    def test_questions_and_settings_lock_at_start(self):
        start_test(self.t, actor=self.lecturer)
        with self.assertRaises(ValueError):
            add_question(self.t, actor=None, kind="tf", text="q", answer_key="TRUE")
        with self.assertRaises(ValueError):
            delete_question(self.t.questions.first(), actor=None)
        with self.assertRaises(ValueError):
            update_settings(self.t, actor=None, title="New", n_objective=1,
                            n_tf=0, n_subjective=0, seconds_objective=20,
                            seconds_tf=20, seconds_subjective=60)


class JoinLifecycleTests(TestCase):
    def setUp(self):
        self.t = make_test(n_obj=2)
        self.s = make_student_enrolled()
        enroll(self.t.course, self.s)
        for _ in range(3):
            add_mcq(self.t)

    def test_five_states(self):
        self.assertEqual(join_state(self.t, student=self.s)[0], "upcoming")
        open_test(self.t)
        self.assertEqual(join_state(self.t, student=self.s)[0], "open")
        a = start_attempt(self.t, student=self.s)
        self.assertEqual(join_state(self.t, student=self.s)[0], "in_progress")
        a.expires_objective = timezone.now() - timedelta(seconds=30)
        a.save()
        finalize(a)
        self.assertEqual(join_state(self.t, student=self.s)[0], "submitted")
        close_test(self.t, actor=self.t.created_by)
        state, _ = join_state(self.t, student=self.s)
        self.assertEqual(state, "submitted")  # has an attempt, finalized

    def test_draw_is_per_section_and_ordered(self):
        t2 = make_test(n_obj=2, n_tf=1, n_short=1)
        enroll(t2.course, self.s)
        for _ in range(3):
            add_mcq(t2)
        add_tf(t2)
        add_tf(t2, text="Ice floats.", key="TRUE")
        add_short(t2)
        add_short(t2, text="Another?", accepted="x")
        open_test(t2)
        a = start_attempt(t2, student=self.s)
        self.assertEqual(a.drawn_questions().__len__(), 4)
        kinds = [q.kind for q in a.drawn_questions()]
        self.assertEqual(kinds, ["mcq", "mcq", "tf", "short"])  # grouped, sections in order
        self.assertEqual(a.current_section, "objective")

    def test_retry_safe_same_attempt(self):
        open_test(self.t)
        a = start_attempt(self.t, student=self.s)
        again = start_attempt(self.t, student=self.s)
        self.assertEqual(again.id, a.id)

    def test_first_section_deadline_from_test_settings(self):
        self.t.seconds_objective = 30
        self.t.save()
        open_test(self.t)
        a = start_attempt(self.t, student=self.s)
        expected = round((a.expires_objective - a.started_at).total_seconds())
        self.assertEqual(expected, 60)  # 2 drawn x 30s
        self.assertIsNone(a.expires_tf)
        self.assertEqual(a.duration_seconds(), 60)

    def test_refused_before_start_and_after_close(self):
        with self.assertRaises(ValueError):
            start_attempt(self.t, student=self.s)
        open_test(self.t)
        close_test(self.t, actor=self.t.created_by)
        with self.assertRaises(ValueError):
            start_attempt(self.t, student=self.s)

    def test_non_enrolled_cannot_start(self):
        open_test(self.t)
        outsider = make_student_enrolled(reg="MOUAU/PSB/26/070009")
        with self.assertRaises(ValueError):
            start_attempt(self.t, student=outsider)


class SectionWalkTests(TestCase):
    def setUp(self):
        self.t = make_test(n_obj=1, n_tf=1, n_short=1)
        self.s = make_student_enrolled()
        enroll(self.t.course, self.s)
        add_mcq(self.t)
        add_tf(self.t)
        add_short(self.t)
        open_test(self.t)
        self.a = start_attempt(self.t, student=self.s)

    def test_advance_sets_each_deadline_from_its_own_start(self):
        mcq, tf, short = self.a.drawn_questions()
        self.assertEqual(self.a.current_section, "objective")
        save_answer(self.a, question_id=mcq.id, choice="B")
        first_deadline = self.a.expires_objective
        advance_section(self.a)
        self.assertEqual(self.a.current_section, "tf")
        self.assertLess(self.a.section_started_at, timezone.now() + timedelta(seconds=2))
        expected = round((self.a.expires_tf - self.a.section_started_at).total_seconds())
        self.assertEqual(expected, 20)
        self.assertEqual(self.a.expires_objective, first_deadline)  # past stays put
        save_answer(self.a, question_id=tf.id, choice="FALSE")  # the key on this question
        advance_section(self.a)
        self.assertEqual(self.a.current_section, "subjective")
        expected = round((self.a.expires_subjective - self.a.section_started_at).total_seconds())
        self.assertEqual(expected, 60)
        save_answer(self.a, question_id=short.id, text="mitochondrion")
        advance_section(self.a)  # last section: submitting
        self.a.refresh_from_db()
        self.assertIsNotNone(self.a.submitted_at)
        self.assertEqual(self.a.score(), 3)

    def test_earlier_sections_sealed(self):
        mcq, tf, short = self.a.drawn_questions()
        advance_section(self.a)  # now in tf
        with self.assertRaises(ValueError):
            save_answer(self.a, question_id=mcq.id, choice="A")
        with self.assertRaises(ValueError):
            save_answer(self.a, question_id=short.id, text="x")  # future section too

    def test_save_refused_past_deadline_plus_grace(self):
        mcq, _, _ = self.a.drawn_questions()
        self.a.expires_objective = timezone.now() - timedelta(seconds=5)
        self.a.save()
        save_answer(self.a, question_id=mcq.id, choice="B")  # inside the 10s grace
        self.a.expires_objective = timezone.now() - timedelta(seconds=30)
        self.a.save()
        with self.assertRaises(ValueError):
            save_answer(self.a, question_id=mcq.id, choice="A")

    def test_late_submit_refused_but_finalize_seals(self):
        mcq, _, _ = self.a.drawn_questions()
        save_answer(self.a, question_id=mcq.id, choice="B")
        self.a.expires_objective = timezone.now() - timedelta(minutes=2)
        self.a.save()
        with self.assertRaises(ValueError):
            submit(self.a)
        finalize(self.a)
        self.a.refresh_from_db()
        self.assertIsNotNone(self.a.submitted_at)  # auto-submitted at expiry
        with self.assertRaises(ValueError):
            save_answer(self.a, question_id=mcq.id, choice="A")

    def test_submit_then_frozen(self):
        mcq, _, _ = self.a.drawn_questions()
        save_answer(self.a, question_id=mcq.id, choice="B")
        submit(self.a)
        with self.assertRaises(ValueError):
            save_answer(self.a, question_id=mcq.id, choice="A")

    def test_skipped_section_draws_nothing(self):
        t2 = make_test(n_obj=1, n_tf=0, n_short=1)
        enroll(t2.course, self.s)
        add_mcq(t2)
        add_short(t2)
        open_test(t2)
        a = start_attempt(t2, student=self.s)
        self.assertEqual(a.current_section, "objective")
        advance_section(a)
        self.assertEqual(a.current_section, "subjective")  # tf skipped entirely
        self.assertIsNone(a.expires_tf)


class AnsweringTests(TestCase):
    def setUp(self):
        self.t = make_test(n_obj=2)
        open_test(self.t)
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

    def test_grading_across_sections(self):
        t2 = make_test(self.t.course, n_obj=1, n_short=1)  # two active sections
        mcq = add_mcq(t2)
        short = add_short(t2, accepted="Chlorophyll")
        open_test(t2)
        a = start_attempt(t2, student=self.s)
        self.assertEqual(a.current_section, "objective")
        save_answer(a, question_id=mcq.id, choice="B")  # correct, objective live
        advance_section(a)  # tf is empty, so subjective is next and now live
        save_answer(a, question_id=short.id, text="  chlorophyll.  ")  # messy but matches
        self.assertEqual(a.score(), 2)
        save_answer(a, question_id=short.id, text="chloroplast")
        self.assertEqual(a.score(), 1)  # wrong variant, no point


class DeleteFloorTests(TestCase):
    def test_floor_is_per_section(self):
        t = make_test(n_obj=1, n_tf=1)
        add_mcq(t)
        add_mcq(t, text="Second mcq", key="A", options="x\ny")
        add_tf(t)
        delete_question(t.questions.filter(kind="mcq").first(), actor=None)  # pool 2 -> 1, fine
        with self.assertRaises(ValueError):
            delete_question(t.questions.filter(kind="mcq").first(), actor=None)  # pool 1 == draw 1
        with self.assertRaises(ValueError):
            delete_question(t.questions.filter(kind="tf").first(), actor=None)  # pool 1 == draw 1


class ReleaseTests(TestCase):
    def setUp(self):
        self.t = make_test(n_obj=1, n_short=1)
        open_test(self.t)
        self.s = make_student_enrolled()
        enroll(self.t.course, self.s)
        self.mcq = add_mcq(self.t)
        self.short = add_short(self.t, accepted="Chlorophyll")
        self.a = start_attempt(self.t, student=self.s)
        save_answer(self.a, question_id=self.mcq.id, choice="B")
        advance_section(self.a)
        save_answer(self.a, question_id=self.short.id, text="Chlorophyll")
        submit(self.a)

    def test_release_requires_started_test(self):
        draft = make_test(n_obj=1)
        with self.assertRaises(ValueError):
            release_results(draft, actor=draft.created_by)

    def test_release_closes_and_scores_visible(self):
        release_results(self.t, actor=self.t.created_by)
        self.t.refresh_from_db()
        self.assertIsNotNone(self.t.results_released_at)
        self.assertIsNotNone(self.t.closed_at)
        state, attempt = join_state(self.t, student=self.s)
        self.assertEqual(state, "released")
        self.assertEqual(attempt.score(), 2)
        self.assertTrue(AuditLog.objects.filter(action="test.release").exists())

    def test_release_finalizes_running_attempts(self):
        self.s2 = make_student_enrolled(reg="MOUAU/PSB/26/070002")
        enroll(self.t.course, self.s2)
        add_mcq(self.t, text="Extra for second draw", key="A", options="x\ny")
        running = start_attempt(self.t, student=self.s2)
        release_results(self.t, actor=self.t.created_by)
        running.refresh_from_db()
        self.assertIsNotNone(running.submitted_at)


class CloneTests(TestCase):
    def test_clone_copies_questions_into_fresh_draft(self):
        t = make_test(n_obj=2, n_tf=1, n_short=0, seconds_subjective=90, points_per_question=2)
        add_mcq(t)
        add_mcq(t, text="Water is?", key="A", options="H2O\nCO2")
        add_tf(t)
        start_test(t, actor=t.created_by)
        c = clone_test(t, actor=t.created_by)
        self.assertNotEqual(c.id, t.id)
        self.assertTrue(c.title.endswith("(copy)"))
        self.assertEqual(c.status, "draft")  # runs its own lifecycle from scratch
        self.assertNotEqual(c.join_code, t.join_code)
        self.assertEqual((c.n_objective, c.n_tf), (2, 1))
        self.assertEqual(c.seconds_subjective, 90)
        self.assertEqual(c.points_per_question, 2)
        self.assertEqual(
            list(c.questions.values_list("text", flat=True)),
            list(t.questions.values_list("text", flat=True)),
        )
        self.assertTrue(AuditLog.objects.filter(action="test.clone").exists())
        # editing the copy leaves the original untouched
        add_mcq(c, text="Added to the copy", key="C", options="x\ny\nz")
        self.assertEqual(c.questions.count(), 4)
        self.assertEqual(t.questions.count(), 3)


class CodeTests(TestCase):
    def test_regen_changes_code_and_audits(self):
        t = make_test()
        old = t.join_code
        regenerate_join_code(t, actor=t.created_by)
        self.assertNotEqual(t.join_code, old)
        self.assertTrue(AuditLog.objects.filter(action="test.regen_code").exists())
