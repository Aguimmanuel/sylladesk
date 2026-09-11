from django.contrib import messages
from django.contrib.auth import get_user_model, login, update_session_auth_hash
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
