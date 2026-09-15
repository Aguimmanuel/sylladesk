import logging
import smtplib

from django.db import transaction
from django.shortcuts import redirect

from courses.models import RosterEntry
from courses.services import claim_roster_entries

from .forms import LoudPasswordResetForm
from .services import signup_throttle_check_and_hit

from django.contrib import messages
logger = logging.getLogger(__name__)
from django.contrib.auth import get_user_model, login, update_session_auth_hash
from django.contrib.auth import views as auth_views
from django.contrib.auth.views import LoginView, LogoutView, PasswordChangeView
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic import FormView

from core.auditing import audit

from .forms import LoginForm, PasswordSetForm

User = get_user_model()


class LoginView(LoginView):
    """FR-01/04. django-axes provides the lockout; FR-01 middleware provides the
    forced-reset redirect. Template: accounts/login.html."""

    template_name = "accounts/login.html"
    authentication_form = LoginForm
    redirect_authenticated_user = True

    def form_valid(self, form):
        response = super().form_valid(form)
        audit(actor=self.request.user, action="auth.login", obj=self.request.user)
        return response


class LogoutView(LogoutView):
    pass


class PasswordSetView(FormView):
    """The one page a temp-credential user may see (FR-01)."""

    template_name = "accounts/password_set.html"
    form_class = PasswordSetForm
    success_url = reverse_lazy("home")

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated or not request.user.must_reset_password:
            return redirect("home")
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        user = self.request.user
        user.set_password(form.cleaned_data["new_password1"])
        user.must_reset_password = False
        user.save(update_fields=["password", "must_reset_password"])
        update_session_auth_hash(self.request, user)  # keep the session, don't log them out
        audit(actor=user, action="auth.password_set", obj=user, detail={"forced": True})
        messages.success(self.request, "Password set — welcome aboard.")
        return super().form_valid(form)


class PasswordChangeView(PasswordChangeView):
    template_name = "accounts/password_change.html"
    success_url = reverse_lazy("home")

    def form_valid(self, form):
        response = super().form_valid(form)
        audit(actor=self.request.user, action="auth.password_change", obj=self.request.user)
        messages.success(self.request, "Password changed.")
        return response


def _names_match(signup_name: str, entry) -> bool:
    """Case/space-insensitive comparison when the roster row carries a name."""
    if not entry.full_name:
        return True  # neutral — row has no name to compare
    norm = lambda s: " ".join(s.casefold().split())
    return norm(signup_name) == norm(entry.full_name)


class StudentSignupView(FormView):
    """FR-33: signup ONLY against the lecturer's authenticated roster.
    One account per reg number; name-match where roster has names;
    auto-enrolls in every course listing that number; rate-limited; audited."""

    template_name = "accounts/signup.html"
    form_class = None  # set below to avoid circular import at module load
    success_url = reverse_lazy("home")

    def get_form_class(self):
        from .signup_forms import StudentSignupForm
        return StudentSignupForm

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect("home")
        return super().dispatch(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        ip = request.META.get("REMOTE_ADDR", "0.0.0.0")
        if not signup_throttle_check_and_hit(ip):
            messages.error(request, "Too many signup attempts. Try again in a minute.")
            return redirect("accounts:login")
        return super().post(request, *args, **kwargs)

    def form_valid(self, form):
        reg = form.cleaned_data["reg_no"]
        name = form.cleaned_data["full_name"]

        entries = list(
            RosterEntry.objects.select_related("course")
            .filter(reg_no=reg, is_active=True)
        )
        if not entries:
            form.add_error("reg_no",
                "This registration number is not on any course roster. Contact your lecturer.")
            return self.form_invalid(form)
        if any(e.claimed_by_id for e in entries):
            form.add_error("reg_no",
                "This registration number has already been registered. Try logging in instead.")
            return self.form_invalid(form)
        named = [e for e in entries if e.full_name]
        if named and not any(_names_match(name, e) for e in named):
            form.add_error("full_name",
                "Name does not match the roster. Use your name exactly as your lecturer submitted it.")
            return self.form_invalid(form)
        User = get_user_model()

        email = form.cleaned_data["email"].strip()
        if User.objects.filter(email__iexact=email).exists():
            form.add_error("email", "This email is already in use.")
            return self.form_invalid(form)
        try:
            with transaction.atomic():
                # re-claim atomically: unclaimed rows only, locked to prevent races
                unclaimed = RosterEntry.objects.select_for_update().filter(
                    reg_no=reg, claimed_by__isnull=True, is_active=True
                )
                if not unclaimed.exists():
                    form.add_error("reg_no",
                        "This registration number has already been registered.")
                    return self.form_invalid(form)
                user = User(
                    username=reg, reg_no=reg, full_name=name,
                    email=email,
                    global_role=User.GlobalRole.STUDENT,
                )
                user.set_password(form.cleaned_data["password1"])
                user.save()
                joined = claim_roster_entries(user)
        except Exception:
            form.add_error(None, "Could not create the account (possibly already registered).")
            return self.form_invalid(form)

        audit(actor=user, action="student.signup", obj=user,
              detail={"courses": [c.code for c in joined]})
        login(self.request, user, backend="django.contrib.auth.backends.ModelBackend")
        messages.success(self.request,
            f"Welcome, {name}! You're enrolled in {len(joined)} course(s).")
        return super().form_valid(form)


class ThrottledPasswordResetView(auth_views.PasswordResetView):
    """V2-13: 'Forgot password?' - emails a 1-hour reset link (Gmail SMTP).
    Same per-IP throttle as signup, tighter budget (10/hour). Generic success
    page: the response must NOT reveal whether the address has an account."""

    form_class = LoudPasswordResetForm  # loud: send failures reach form_valid's handler
    template_name = "registration/password_reset_form.html"
    email_template_name = "registration/password_reset_email.html"
    subject_template_name = "registration/password_reset_subject.txt"
    success_url = reverse_lazy("accounts:password_reset_done")

    def post(self, request, *args, **kwargs):
        ip = request.META.get("REMOTE_ADDR", "0.0.0.0")
        if not signup_throttle_check_and_hit(ip, limit=10, window_seconds=3600):
            messages.error(request, "Too many reset requests. Try again in a bit.")
            return redirect("accounts:login")
        return super().post(request, *args, **kwargs)

    def form_valid(self, form):
        try:
            return super().form_valid(form)
        except (smtplib.SMTPException, OSError):
            # Render's FREE tier blocks outbound SMTP ports entirely (since
            # 2025-09); providers also have ordinary outages, and an App
            # Password can be wrong. None of that may crash a worker or show
            # the student a 500. Log server-side; tell the student the truth.
            logger.exception("Password-reset email could not be sent")
            messages.error(self.request,
                "We could not send the reset email right now. "
                "Please contact your lecturer to reset your password.")
            return redirect("accounts:login")


class PasswordResetDone(auth_views.PasswordResetDoneView):
    """The done page reads `email_configured` from the brand() context processor:
    when no EMAIL_HOST_USER is configured, it says honestly that no mail went out."""
    template_name = "registration/password_reset_done.html"


class ResetConfirm(auth_views.PasswordResetConfirmView):
    """Sets the new password. ALSO clears the forced-reset flag if it was set:
    a student with a temp credential who resets by email must not be bounced
    into setting a password twice."""

    template_name = "registration/password_reset_confirm.html"
    success_url = reverse_lazy("accounts:password_reset_complete")

    def form_valid(self, form):
        response = super().form_valid(form)
        user = form.user
        if getattr(user, "must_reset_password", False):
            user.must_reset_password = False
            user.save(update_fields=["must_reset_password"])
            audit(actor=user, action="auth.reset_cleared_forced_flag", obj=user)
        return response


class PasswordResetComplete(auth_views.PasswordResetCompleteView):
    template_name = "registration/password_reset_complete.html"
