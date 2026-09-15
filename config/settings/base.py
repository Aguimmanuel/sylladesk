"""
Shared settings. Development/production override what differs.
Everything environment-specific comes from .env (12-factor, FR-25/ops).
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
    "axes",  # login rate-limiting (FR-04)
    # project apps (PROJECT-STRUCTURE.md)
    "core",
    "accounts",
    "courses",
    "materials",
    # "django_tasks" + "django_tasks.backends.database" land in Phase 5 (assessments)
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
    "accounts.middleware.MustResetPasswordMiddleware",  # FR-01: temp credentials must reset first
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
     "OPTIONS": {"min_length": 10}},  # FR-04
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",  # FR-04 / research section 5
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher",
]

# --- django-axes: 5 failed logins / 15 min cooldown per username+IP (FR-04) ---
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
# ── Email (V2-13 forgot-password, shipped as Phase 2 pull) ──────────
# Local dev: unset -> console backend (reset emails print to the terminal).
# Production: set ALL of the EMAIL_* values in Render (Gmail App Password).
# Swapping to Resend later = changing these env values only, zero code.
EMAIL_BACKEND = env("EMAIL_BACKEND", default="django.core.mail.backends.console.EmailBackend")
EMAIL_HOST = env("EMAIL_HOST", default="")
EMAIL_PORT = env.int("EMAIL_PORT", default=587)
EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS", default=True)
EMAIL_HOST_USER = env("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", default="")
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="SyllaDesk <no-reply@sylladesk.local>")
PASSWORD_RESET_TIMEOUT = 60 * 60  # reset links die after 1 hour

FILES_BACKEND = env("FILES_BACKEND", default="db")  # "db" (free hosting) | "disk" (VPS)
FILES_DISK_ROOT = Path(env("FILES_DISK_ROOT", default=str(BASE_DIR / "var" / "files")))
MATERIAL_MAX_MB = 30   # FR-07
SUBMISSION_MAX_MB = 15  # FR-11

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

LANGUAGE_CODE = "en"
TIME_ZONE = "Africa/Lagos"   # display tz; everything stored UTC (D-13)
USE_I18N = True
USE_TZ = True

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"  # BIGINT PKs (PRD section 3.2)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "INFO"},
}
