from django import forms

from .models import Course


class CourseForm(forms.ModelForm):
    class Meta:
        model = Course
        fields = ["code", "title", "session", "semester"]
        widgets = {
            "code": forms.TextInput(attrs={"placeholder": "PSB 413"}),
            "title": forms.TextInput(attrs={"placeholder": "Cytogenetics Of Plants"}),
            "session": forms.TextInput(attrs={"placeholder": "2025/2026"}),
        }


class RosterUploadForm(forms.Form):
    roster_file = forms.FileField(
        label="Roster CSV",
        help_text="Columns: registration_number, full_name (optional). Saved as this course's authenticated list.",
    )
