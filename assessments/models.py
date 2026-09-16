"""Timed tests: question pool, join codes, per-student attempts, answers.

Questions live in three sections - objective (multiple choice), true/false
and subjective (short answer). Each attempt draws a set number of questions
per section and works through the sections in order, one countdown per
section. Scores are computed from answers at read time and stay hidden until
the lecturer releases results.
"""
import secrets

from django.conf import settings
from django.db import models

from courses.models import Course

from .grading import grade_objective, grade_subjective

# unambiguous alphabet: no 0/O or 1/I, which read alike on paper
CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
SECONDS_OBJECTIVE = 20
SECONDS_TF = 20
SECONDS_SUBJECTIVE = 60

# question kind -> section key; the three sections are the three kinds
SECTION_OF_KIND = {"mcq": "objective", "tf": "tf", "short": "subjective"}


def make_join_code():
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(6))


class Test(models.Model):
    course = models.ForeignKey(Course, on_delete=models.PROTECT, related_name="tests")
    title = models.CharField(max_length=200)
    join_code = models.CharField(max_length=6, unique=True, db_index=True, default=make_join_code)
    # draw sizes: how many of each kind one attempt answers
    n_objective = models.PositiveIntegerField(default=0)
    n_tf = models.PositiveIntegerField(default=0)
    n_subjective = models.PositiveIntegerField(default=0)
    points_per_question = models.PositiveIntegerField(default=1)
    # pacing: seconds per question in each section, chosen per test
    seconds_objective = models.PositiveIntegerField(default=SECONDS_OBJECTIVE)
    seconds_tf = models.PositiveIntegerField(default=SECONDS_TF)
    seconds_subjective = models.PositiveIntegerField(default=SECONDS_SUBJECTIVE)
    allow_review = models.BooleanField(default=False)
    # the lecturer opens and closes the test by hand; no scheduled times
    started_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    results_released_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="tests_created"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.course.code} - {self.title}"

    def sections(self):
        """The three sections in the order students meet them."""
        return [
            {"key": "objective", "kind": Question.Kind.MCQ, "label": "Objective",
             "n": self.n_objective, "seconds": self.seconds_objective},
            {"key": "tf", "kind": Question.Kind.TF, "label": "True / False",
             "n": self.n_tf, "seconds": self.seconds_tf},
            {"key": "subjective", "kind": Question.Kind.SHORT, "label": "Subjective",
             "n": self.n_subjective, "seconds": self.seconds_subjective},
        ]

    def active_sections(self):
        return [s for s in self.sections() if s["n"] > 0]

    @property
    def n_drawn_total(self):
        return self.n_objective + self.n_tf + self.n_subjective

    @property
    def max_score(self):
        return self.n_drawn_total * self.points_per_question

    @property
    def status(self):
        if self.results_released_at:
            return "released"
        if self.closed_at:
            return "closed"
        if self.started_at:
            return "live"
        return "draft"


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
    """One attempt per student per test. The draw is fixed the moment the
    attempt starts; each section's deadline is fixed when the student enters
    it. The server clock rules."""

    # which model field holds each section's deadline
    SECTION_FIELD = {
        "objective": "expires_objective",
        "tf": "expires_tf",
        "subjective": "expires_subjective",
    }
    SECTION_CHOICES = [
        ("objective", "Objective"),
        ("tf", "True / False"),
        ("subjective", "Subjective"),
    ]

    test = models.ForeignKey(Test, on_delete=models.PROTECT, related_name="attempts")
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="test_attempts"
    )
    drawn_ids = models.TextField()  # comma-separated question ids, grouped by section in order
    started_at = models.DateTimeField(auto_now_add=True)
    current_section = models.CharField(max_length=12, choices=SECTION_CHOICES, default="objective")
    section_started_at = models.DateTimeField(null=True, blank=True)
    expires_objective = models.DateTimeField(null=True, blank=True)
    expires_tf = models.DateTimeField(null=True, blank=True)
    expires_subjective = models.DateTimeField(null=True, blank=True)
    submitted_at = models.DateTimeField(null=True, blank=True)  # null while in progress

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["test", "student"], name="uniq_attempt_test_student")
        ]

    def deadline(self):
        """Deadline of the section the student is in now."""
        return getattr(self, self.SECTION_FIELD[self.current_section], None)

    def final_deadline(self):
        deadlines = [d for d in (self.expires_objective, self.expires_tf, self.expires_subjective) if d]
        return max(deadlines) if deadlines else self.started_at

    def drawn_questions(self):
        ids = [int(i) for i in self.drawn_ids.split(",") if i]
        qs = {q.id: q for q in Question.objects.filter(id__in=ids)}
        return [qs[i] for i in ids if i in qs]

    def section_questions(self):
        """Drawn questions grouped by section key, in draw order."""
        grouped = {"objective": [], "tf": [], "subjective": []}
        for q in self.drawn_questions():
            grouped[SECTION_OF_KIND[q.kind]].append(q)
        return grouped

    def duration_seconds(self):
        secs = {
            "objective": self.test.seconds_objective,
            "tf": self.test.seconds_tf,
            "subjective": self.test.seconds_subjective,
        }
        return sum(secs[SECTION_OF_KIND[q.kind]] for q in self.drawn_questions())

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
