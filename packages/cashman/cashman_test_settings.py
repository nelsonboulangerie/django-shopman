"""Settings mínimos para rodar a suíte do shopman.cashman isolada."""

SECRET_KEY = "test-secret-key-for-cashman-tests"

DEBUG = True

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "shopman.cashman",
]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

USE_TZ = True
TIME_ZONE = "America/Sao_Paulo"
