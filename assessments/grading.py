"""The grading module: pure functions from (response, key) -> points.

Deliberately isolated so a different grader can slot in later without
touching schema, data, or views.
"""
import re

_TRAILING_PUNCT = re.compile(r"[.,;:!?\s]+$")


def normalize_answer(text):
    """Lowercase, trim, collapse spaces, drop trailing punctuation."""
    t = " ".join((text or "").split()).lower()
    return _TRAILING_PUNCT.sub("", t)


def grade_objective(question, choice):
    """Exact key match for MCQ letters and true/false."""
    return choice.strip().upper() == question.answer_key.strip().upper()


def grade_subjective(question, text):
    """Case/space/punctuation-insensitive match against any accepted variant."""
    return normalize_answer(text) in question.key_variants()
