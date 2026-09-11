from django import forms
from django.contrib.auth import password_validation
from django.contrib.auth.forms import AuthenticationForm


class LoginForm(AuthenticationForm):
    """FR-01: username (reg no for students, email for staff) + password.
    django-axes wraps authentication — the view code stays stock."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].widget.attrs.update(
            {"autofocus": True, "placeholder": "Reg no or email", "inputmode": "text"}
        )
        self.fields["password"].widget.attrs.update({"placeholder": "Password"})


class PasswordSetForm(forms.Form):
    """Forced first-login reset (FR-01) — runs the standard validators (min 10, FR-04)."""

    new_password1 = forms.CharField(
        label="New password", strip=False, widget=forms.PasswordInput(attrs={"autocomplete": "new-password"})
    )
    new_password2 = forms.CharField(
        label="Confirm new password", strip=False, widget=forms.PasswordInput(attrs={"autocomplete": "new-password"})
    )

    def clean_new_password1(self):
        p1 = self.cleaned_data.get("new_password1")
        password_validation.validate_password(p1)
        return p1

    def clean(self):
        cleaned = super().clean()
        p1, p2 = cleaned.get("new_password1"), cleaned.get("new_password2")
        if p1 and p2 and p1 != p2:
            self.add_error("new_password2", "The two passwords didn't match.")
        return cleaned
