"""Local development (and sandbox preview): verbose, permissive, PostgreSQL via Docker
by default. Dev-only wildcard host; production requires an explicit ALLOWED_HOSTS."""
from .base import *  # noqa: F401,F403

DEBUG = True
ALLOWED_HOSTS = ["*"]
