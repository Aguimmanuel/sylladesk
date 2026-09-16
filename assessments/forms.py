from django import forms
from django.utils import timezone

from .models import Question, Test


class TestForm(forms.ModelForm):
    class Meta:
        model = Test
        fields = ["title", "open_at", "close_at", "n_to_answer", "points_per_question", "allow_review"]
        widgets = {
            "title": forms.TextInput(attrs={"placeholder": "Week 4 Quiz"}),
            "open_at": forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
            "close_at": forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for f in ("open_at", "close_at"):
            self.fields[f].input_formats = ["%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M"]


class QuestionForm(forms.Form):
    KIND_CHOICES = [("mcq", "Multiple choice"), ("tf", "True / False"), ("short", "Short answer")]
    kind = forms.ChoiceField(choices=KIND_CHOICES, widget=forms.RadioSelect)
    text = forms.CharField(widget=forms.Textarea(attrs={"rows": 3}))
    options = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 4}),
                              help_text="Multiple choice only: one option per line. The first line is option A.")
    answer_key = forms.CharField(required=False, help_text="Multiple choice: the letter (A, B, ...). True/False: True or False.")
    accepted_answers = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 3}),
                                       help_text="Short answer only: 1 to 5 accepted answers, one per line.")


class JoinForm(forms.Form):
    code = forms.CharField(max_length=6, min_length=6,
                           widget=forms.TextInput(attrs={"placeholder": "ABC123", "style": "text-transform: uppercase"}))
