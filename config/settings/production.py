"""Production: secrets required, HTTPS enforced, manifest static files (F1 Render or R1 VPS)."""
import sys
import warnings

from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F401,F403

DEBUG = False
SECRET_KEY = env("SECRET_KEY")  # required — no default in production
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS")  # required

SECURE_SSL_REDIRECT = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 31_536_000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"
    },
}

# Offsite backups run from GitHub Actions via scripts/backup.sh. Until
# BACKUP_TARGET is set, warn at boot instead of refusing; Neon keeps ~7 days
# of point-in-time history in the meantime.
if "collectstatic" not in sys.argv and "makemigrations" not in sys.argv:
    if not env("BACKUP_TARGET", default=""):
        warnings.warn(
            "BACKUP_TARGET is not set — running without offsite backups. "
            "Wire scripts/backup.sh to B2/R2 before loading real student data (DoD #8).",
            RuntimeWarning,
            stacklevel=1,
        )
