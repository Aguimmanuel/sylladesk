"""
Shared settings. Development/production override what differs.
Everything environment-specific comes from .env.
"""
from datetime import timedelta
from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env(DEBUG=(bool, False))
environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("SECRET_KEY", default="dev-insecure-key-DO-NOT-USE-IN-PRODUCTION")
DEBUG = env("DEBUG")
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # third-party
    "axes",  # login rate-limiting
    # project apps
    "core",
    "accounts",
    "courses",
    "materials",
    "assignments",
    "assessments",
    "announcements",
    # django_tasks lands with assessments
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "axes.middleware.AxesMiddleware",
    "accounts.middleware.MustResetPasswordMiddleware",  # temp credentials must reset first
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.template.context_processors.csrf",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "core.context_processors.brand",
            ],
        },
    },
]

DATABASES = {
    "default": env.db(
        "DATABASE_URL",
        default="postgres://lms:lms@localhost:5432/lms",  # Docker compose default
    )
}
# SQLite convenience: DATABASE_URL=sqlite:///var/dev.sqlite3 means
# "<project>/var/dev.sqlite3" — NOT the system /var. Folder auto-created.
_db = DATABASES["default"]
if _db["ENGINE"].endswith("sqlite3"):
    _name = Path(_db["NAME"])
    if _name.is_absolute() and _name.parts[:2] == ("/", "var"):
        _name = BASE_DIR / "var" / _name.name
    _name.parent.mkdir(parents=True, exist_ok=True)
    _db["NAME"] = str(_name)

# Postgres is the locked engine (D-01). SQLite is allowed ONLY as a CI/sandbox smoke override
# via DATABASE_URL — it is never used in development or production.

AUTH_USER_MODEL = "accounts.User"

LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "home"
LOGOUT_REDIRECT_URL = "accounts:login"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
     "OPTIONS": {"min_length": 10}},  # minimum 10 characters
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",  # modern password hashing
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher",
]

# --- django-axes: 5 failed logins -> 15 min lockout per username+IP ---
AUTHENTICATION_BACKENDS = [
    "axes.backends.AxesStandaloneBackend",
    "django.contrib.auth.backends.ModelBackend",
]
AXES_FAILURE_LIMIT = 5
AXES_COOLOFF_TIME = timedelta(minutes=15)
AXES_LOCKOUT_PARAMETERS = [["username", "ip_address"]]
AXES_RESET_ON_SUCCESS = True
AXES_ENABLED = env.bool("AXES_ENABLED", default=True)

# --- files (PRD section 3.2, core.storage is the F1<->R1 seam) ---
# ── Email ──────────────────────────────────────────────────────────
# No EMAIL_HOST locally: mail prints to the terminal. On the server the
# backend is chosen automatically from the environment.
EMAIL_HOST = env("EMAIL_HOST", default="")
APPS_SCRIPT_MAIL_URL = env("APPS_SCRIPT_MAIL_URL", default="")
APPS_SCRIPT_MAIL_TOKEN = env("APPS_SCRIPT_MAIL_TOKEN", default="")
_explicit_backend = env("EMAIL_BACKEND", default=None)
if _explicit_backend:
    EMAIL_BACKEND = _explicit_backend  # explicit env always wins
elif APPS_SCRIPT_MAIL_URL and APPS_SCRIPT_MAIL_TOKEN:
    EMAIL_BACKEND = "core.mail_backends.AppsScriptMailBackend"  # free HTTPS route
elif EMAIL_HOST:
    EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"  # works off Render-free
else:
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"  # dev: mail to terminal
EMAIL_TIMEOUT = env.int("EMAIL_TIMEOUT", default=15)  # seconds
EMAIL_PORT = env.int("EMAIL_PORT", default=587)
EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS", default=True)
EMAIL_HOST_USER = env("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", default="")
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="SyllaDesk <no-reply@sylladesk.local>")
PASSWORD_RESET_TIMEOUT = 60 * 60  # reset links die after 1 hour

FILES_BACKEND = env("FILES_BACKEND", default="db")  # "db" (free hosting) | "disk" (VPS)
FILES_DISK_ROOT = Path(env("FILES_DISK_ROOT", default=str(BASE_DIR / "var" / "files")))
MATERIAL_MAX_MB = 30   # lecture material cap
SUBMISSION_MAX_MB = 15  # assignment submission cap

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

LANGUAGE_CODE = "en"
TIME_ZONE = "Africa/Lagos"   # display timezone; stored UTC
USE_I18N = True
USE_TZ = True

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"  # BIGINT PKs (PRD section 3.2)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "INFO"},
}
