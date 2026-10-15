from django.apps import AppConfig


class WatchmanConfig(AppConfig):
    name = "shopman.watchman"
    label = "watchman"
    verbose_name = "Watchman"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self) -> None:
        from shopman.watchman import django_checks  # noqa: F401
