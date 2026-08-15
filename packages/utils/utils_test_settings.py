"""Minimal Django settings for testing shopman.utils."""

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

INSTALLED_APPS = [
    # `unfold` entra para testar o caminho CANÔNICO: o módulo `contrib/admin_unfold`
    # delega aos templates do Unfold em vez de copiar o markup deles, e sem o pacote
    # instalado o teste não veria isso acontecer.
    #
    # O caminho SEM Unfold (que precisa existir: o Unfold é sugerido, não
    # obrigatório) é coberto em `TestWithoutUnfold`, que simula o template ausente
    # e confere que os helpers caem para HTML simples — ainda escapado.
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
