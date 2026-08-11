"""
Django settings for Offerman tests.

Minimal settings to run pytest with shopman.offerman app.
"""

SECRET_KEY = "test-secret-key-for-offerman-tests"

DEBUG = True

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "taggit",
    "simple_history",
    "rest_framework",
    "django_filters",
    "shopman.offerman",
]

ROOT_URLCONF = "shopman.offerman.tests.urls"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
    ],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
}

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

USE_TZ = True
TIME_ZONE = "America/Sao_Paulo"

# Mesma régua do deployment (`config/settings.py`): slug de tag em ASCII, porque é o slug
# que viaja em JSON de regra. Divergir por ambiente faria o teste passar e a produção não.
TAGGIT_STRIP_UNICODE_WHEN_SLUGIFYING = True
