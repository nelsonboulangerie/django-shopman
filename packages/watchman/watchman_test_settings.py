"""Minimal settings for the reusable Watchman package."""

SECRET_KEY = "watchman-tests-not-for-production"
DEBUG = False
ROOT_URLCONF = "watchman_test_urls"
ALLOWED_HOSTS = ["testserver"]
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "shopman.watchman",
]

MIDDLEWARE = [
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
]

WATCHMAN = {
    "CHECKS": ["shopman.watchman.checks.ProcessCheck"],
    "PROFILES": {
        "liveness": ["process"],
        "readiness": ["process"],
        "diagnostic": ["process"],
    },
}
