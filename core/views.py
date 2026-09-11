from django.contrib.auth.decorators import login_required
from django.db import connection
from django.http import JsonResponse
from django.shortcuts import redirect, render

from accounts.models import User  # noqa: F401  (keep the import explicit for readers)


def healthz(request):
    """FR-26: app live + database reachable. 503 when the DB is down."""
    try:
        with connection.cursor() as cur:
            cur.execute("SELECT 1")
        db_ok = True
    except Exception:
        db_ok = False
    return JsonResponse(
        {"status": "ok" if db_ok else "degraded", "database": db_ok},
        status=200 if db_ok else 503,
    )


@login_required
def home(request):
    """Route by global role. Real per-role homes arrive with their phases."""
    user = request.user
    if user.global_role == User.GlobalRole.ADMIN and user.is_staff:
        return redirect("admin:index")
    return render(request, "core/home.html", {"role": user.global_role})
