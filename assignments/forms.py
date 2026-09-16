from django import forms
from django.utils import timezone

from .models import Assignment


class AssignmentForm(forms.ModelForm):
    class Meta:
        model = Assignment
        fields = ["title", "instructions", "max_score", "due_at", "allowed_ext"]
        widgets = {
            "title": forms.TextInput(attrs={"placeholder": "Cell Division Report"}),
            "instructions": forms.Textarea(attrs={"rows": 4}),
            "due_at": forms.DateTimeInput(
                attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["due_at"].input_formats = ["%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M"]

    def clean_due_at(self):
        value = self.cleaned_data["due_at"]
        if timezone.is_naive(value):
            value = timezone.make_aware(value)  # entered in Africa/Lagos, stored UTC
        return value

    def clean_allowed_ext(self):
        exts = ",".join(e.strip().lower() for e in self.cleaned_data["allowed_ext"].split(",") if e.strip())
        return exts or "pdf"


class SubmissionForm(forms.Form):
    submission_file = forms.FileField(label="Your file")
    note = forms.CharField(label="Note to the lecturer (optional)",
                           max_length=1000, required=False,
                           widget=forms.Textarea(attrs={"rows": 3}))


class GradeForm(forms.Form):
    score = forms.IntegerField(min_value=0, required=False)
    score_note = forms.CharField(max_length=500, required=False,
                                 widget=forms.Textarea(attrs={"rows": 2}))
