"""Minimal Django settings for testing shopman.utils."""

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

INSTALLED_APPS = [
    # `unfold` entra porque este pacote tem um módulo `contrib/admin_unfold`, e o
    # que ele faz é justamente delegar aos templates do Unfold em vez de copiar o
    # markup deles. Testar esse módulo sem o Unfold instalado testaria a cópia —
    # a coisa que queremos não ter.
    "unfold",
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "shopman.utils",
]

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "APP_DIRS": True,
        "OPTIONS": {},
    }
]

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
SECRET_KEY = "test-secret-key-not-for-production"
