"""Timed tests: question pool, join codes, per-student attempts, answers.

Every attempt answers N questions drawn from the pool of M. Each correct
answer is worth the test's points_per_question. Scores are computed from
answers at read time and stay hidden until the lecturer releases results.
"""
import secrets

from django.conf import settings
from django.db import models

from courses.models import Course

from .grading import grade_objective, grade_subjective

# unambiguous alphabet: no 0/O or 1/I, which read alike on paper
CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
SECONDS_OBJECTIVE = 20
SECONDS_SUBJECTIVE = 60


def make_join_code():
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(6))


class Test(models.Model):
    course = models.ForeignKey(Course, on_delete=models.PROTECT, related_name="tests")
    title = models.CharField(max_length=200)
    open_at = models.DateTimeField()
    close_at = models.DateTimeField()
    join_code = models.CharField(max_length=6, unique=True, db_index=True, default=make_join_code)
    n_to_answer = models.PositiveIntegerField()
    points_per_question = models.PositiveIntegerField(default=1)
    seconds_objective = models.PositiveIntegerField(default=SECONDS_OBJECTIVE)
    seconds_subjective = models.PositiveIntegerField(default=SECONDS_SUBJECTIVE)
    allow_review = models.BooleanField(default=False)
    results_released_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="tests_created"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["open_at"]

    def __str__(self):
        return f"{self.course.code} - {self.title}"

    @property
    def max_score(self):
        return self.n_to_answer * self.points_per_question


class Question(models.Model):
    class Kind(models.TextChoices):
        MCQ = "mcq", "Multiple choice"
        TF = "tf", "True / False"
        SHORT = "short", "Short answer"

    test = models.ForeignKey(Test, on_delete=models.CASCADE, related_name="questions")
    kind = models.CharField(max_length=6, choices=Kind.choices)
    text = models.TextField()
    options = models.TextField(blank=True)  # MCQ: one option per line; first line is A
    answer_key = models.CharField(max_length=10, blank=True)  # "A".."F" or "TRUE"/"FALSE"
    accepted_answers = models.TextField(blank=True)  # short answer: one variant per line
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order", "id"]

    def option_list(self):
        return [o.strip() for o in self.options.splitlines() if o.strip()]

    def key_variants(self):
        from .grading import normalize_answer
        return [normalize_answer(a) for a in self.accepted_answers.splitlines() if a.strip()]


class Attempt(models.Model):
    """One attempt per student per test. The draw and the expiry are fixed
    the moment the attempt starts; the server clock rules."""

    test = models.ForeignKey(Test, on_delete=models.PROTECT, related_name="attempts")
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="test_attempts"
    )
    drawn_ids = models.TextField()  # comma-separated question ids, in display order
    started_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    submitted_at = models.DateTimeField(null=True, blank=True)  # null while in progress

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["test", "student"], name="uniq_attempt_test_student")
        ]

    def drawn_questions(self):
        ids = [int(i) for i in self.drawn_ids.split(",") if i]
        qs = {q.id: q for q in Question.objects.filter(id__in=ids)}
        return [qs[i] for i in ids if i in qs]

    def duration_seconds(self):
        total = 0
        for q in self.drawn_questions():
            total += self.test.seconds_subjective if q.kind == Question.Kind.SHORT \
                else self.test.seconds_objective
        return total

    def score(self):
        """Computed at read: awarded points over the drawn questions."""
        answers = {a.question_id: a for a in self.answers.all()}
        points = 0
        for q in self.drawn_questions():
            a = answers.get(q.id)
            if not a:
                continue
            if q.kind == Question.Kind.SHORT:
                if a.text and grade_subjective(q, a.text):
                    points += self.test.points_per_question
            elif a.choice and grade_objective(q, a.choice):
                points += self.test.points_per_question
        return points


class Answer(models.Model):
    attempt = models.ForeignKey(Attempt, on_delete=models.CASCADE, related_name="answers")
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name="+")
    choice = models.CharField(max_length=10, blank=True)
    text = models.TextField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["attempt", "question"], name="uniq_answer")
        ]
