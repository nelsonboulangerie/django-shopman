"""
Django settings for Guestman tests.

Minimal settings to run pytest with shopman.guestman app and all contrib modules.
"""

SECRET_KEY = "test-secret-key-for-customers-tests"

DEBUG = True

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "rest_framework",
    "django_filters",
    # Etiquetas de cliente (`CustomerTag`) — modelo de tag PRÓPRIO, mas a app do
    # taggit precisa existir porque o through herda de `GenericTaggedItemBase`.
    "taggit",
    # Guestman core
    "shopman.guestman",
    # Guestman contribs
    "shopman.guestman.contrib.identifiers",
    "shopman.guestman.contrib.preferences",
    "shopman.guestman.contrib.insights",
    "shopman.guestman.contrib.timeline",
    "shopman.guestman.contrib.consent",
    "shopman.guestman.contrib.loyalty",
    "shopman.guestman.contrib.merge",
]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

ROOT_URLCONF = "customers_test_urls"

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

USE_TZ = True
TIME_ZONE = "America/Sao_Paulo"

# Guestman settings
GUESTMAN = {
    "DEFAULT_REGION": "BR",
    "EVENT_CLEANUP_DAYS": 90,
}

# Manychat webhook secret for tests
MANYCHAT_WEBHOOK_SECRET = ""

# Mesma régua do deployment (`config/settings.py`): slug de tag em ASCII, porque é o slug
# que viaja em JSON de regra. Divergir por ambiente faria o teste passar e a produção não.
TAGGIT_STRIP_UNICODE_WHEN_SLUGIFYING = True
