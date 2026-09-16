from django import forms

from .models import Material

MAX_MB_TEXT = "PDF/PPT/PPTX/DOC/DOCX, up to 30 MB"


class MaterialForm(forms.Form):
    title = forms.CharField(max_length=200, widget=forms.TextInput(
        attrs={"placeholder": "Lecture 3 — Photosynthesis II"}))
    week_no = forms.IntegerField(min_value=1, max_value=52, initial=1)
    material_file = forms.FileField(help_text=MAX_MB_TEXT)


class MaterialEditForm(forms.ModelForm):
    class Meta:
        model = Material
        fields = ["title", "week_no"]
