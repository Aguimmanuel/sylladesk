"""FR-01: accounts created with a temp credential must set a real password
before reaching ANY other page. Server-enforced, not a UI suggestion."""
from django.shortcuts import redirect

_ALLOWED_PREFIXES = (
    "/accounts/password/set",
    "/accounts/logout",
    "/static/",
    "/healthz",
)


class MustResetPasswordMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if (
            user is not None
            and user.is_authenticated
            and user.must_reset_password
            and not request.path.startswith(_ALLOWED_PREFIXES)
        ):
            return redirect("accounts:password_set")
        return self.get_response(request)
