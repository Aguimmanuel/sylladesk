from django import forms
from django.contrib.auth import password_validation
from django.contrib.auth.forms import AuthenticationForm, PasswordResetForm
from django.core.mail import EmailMultiAlternatives
from django.template import loader


class LoginForm(AuthenticationForm):
    """FR-01: username (reg no for students, email for staff) + password.
    django-axes wraps authentication — the view code stays stock."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].widget.attrs.update(
            {"autofocus": True, "placeholder": "Registration number (students) or username (staff)", "inputmode": "text"}
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


class LoudPasswordResetForm(PasswordResetForm):
    """Django's stock form SWALLOWS all send errors (logs them, shows the
    student 'check your email' anyway). We want the truth: send failures must
    reach ThrottledPasswordResetView.form_valid so the student is told.
    Same body as stock send_mail, minus the bare except."""

    def send_mail(self, subject_template_name, email_template_name, context,
                  from_email, to_email, html_email_template_name=None):
        subject = loader.render_to_string(subject_template_name, context)
        subject = "".join(subject.splitlines())  # subjects must not contain newlines
        body = loader.render_to_string(email_template_name, context)
        email_message = EmailMultiAlternatives(subject, body, from_email, [to_email])
        if html_email_template_name is not None:
            email_message.attach_alternative(
                loader.render_to_string(html_email_template_name, context), "text/html")
        # Deliberately NO try/except here - failures propagate to the view.
        email_message.send()
