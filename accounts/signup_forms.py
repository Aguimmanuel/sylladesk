"""Student self-signup (FR-33) — allowlist-gated by authenticated roster."""

from django import forms
from django.contrib.auth import password_validation

from core.utils import normalize_reg_no


class StudentSignupForm(forms.Form):
    reg_no = forms.CharField(label="Registration number", max_length=50)
    full_name = forms.CharField(label="Full name", max_length=120)
    email = forms.EmailField(
        label="Email", max_length=254
    )  # account-recovery path (V2-13 prep)
    password1 = forms.CharField(
        label="Password", strip=False, widget=forms.PasswordInput
    )
    password2 = forms.CharField(
        label="Confirm password", strip=False, widget=forms.PasswordInput
    )

    def clean_reg_no(self):
        return normalize_reg_no(self.cleaned_data.get("reg_no"))

    def clean_full_name(self):
        return " ".join(self.cleaned_data.get("full_name", "").split())

    def clean(self):
        cleaned = super().clean()
        p1, p2 = cleaned.get("password1"), cleaned.get("password2")
        if p1 and p2 and p1 != p2:
            self.add_error("password2", "The two passwords didn't match.")
        if p1:
            password_validation.validate_password(p1)
        return cleaned
