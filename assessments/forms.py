from django import forms

from .models import Question, Test


class TestForm(forms.ModelForm):
    class Meta:
        model = Test
        fields = [
            "title", "n_objective", "n_tf", "n_subjective",
            "seconds_objective", "seconds_tf", "seconds_subjective",
            "points_per_question", "is_makeup",
        ]
        widgets = {
            "title": forms.TextInput(attrs={"placeholder": "Week 4 Quiz"}),
        }
        labels = {
            "n_objective": "Multiple choice to draw",
            "n_tf": "True / False to draw",
            "n_subjective": "Short answer to draw",
            "seconds_objective": "Seconds per multiple choice question",
            "seconds_tf": "Seconds per true/false question",
            "seconds_subjective": "Seconds per short answer question",
            "points_per_question": "Points per question",
            "is_makeup": "Makeup test",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for f in ("n_objective", "n_tf", "n_subjective"):
            self.fields[f].min_value = 0
            self.fields[f].max_value = 200
            self.fields[f].widget.attrs["min"] = 0
        for f in ("seconds_objective", "seconds_tf", "seconds_subjective"):
            self.fields[f].min_value = 5
            self.fields[f].max_value = 7200


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
