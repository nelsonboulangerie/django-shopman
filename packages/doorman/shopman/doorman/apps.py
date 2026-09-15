import logging

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _

logger = logging.getLogger("shopman.doorman")

_LOCAL_ONLY_SENDERS = frozenset({
    "shopman.doorman.senders.ConsoleSender",
    "shopman.doorman.senders.LogSender",
})


def configured_local_only_senders(doorman_settings) -> tuple[str, ...]:
    """Return local-only sender classes that production would actually execute."""

    if doorman_settings.DELIVERY_CHAIN:
        configured = {
            doorman_settings.DELIVERY_SENDERS.get(method, "")
            for method in doorman_settings.DELIVERY_CHAIN
        }
    else:
        configured = {doorman_settings.MESSAGE_SENDER_CLASS}
    return tuple(sorted(configured & _LOCAL_ONLY_SENDERS))


class DoormanConfig(AppConfig):
    name = "shopman.doorman"
    label = "doorman"
    verbose_name = _("Gestão do Acesso")
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        # Import signals to register handlers
        # Enforce API key in production
        from django.conf import settings
        from django.core.exceptions import ImproperlyConfigured

        from . import signals  # noqa: F401
        from .conf import get_doorman_settings

        if not settings.DEBUG:
            ds = get_doorman_settings()

            if not ds.ACCESS_LINK_API_KEY:
                raise ImproperlyConfigured(
                    "DOORMAN['ACCESS_LINK_API_KEY'] must be set in production. "
                    "The access link creation endpoint would be unauthenticated. "
                    "Set a strong random key, or if you intentionally don't use "
                    "access link creation, set DOORMAN['ACCESS_LINK_API_KEY'] "
                    "to any non-empty value."
                )

            unsafe_senders = configured_local_only_senders(ds)
            if unsafe_senders:
                raise ImproperlyConfigured(
                    "Emissor local do Doorman selecionado em produção: "
                    + ", ".join(unsafe_senders)
                    + ". Configure um emissor real (WhatsApp, SMS ou e-mail)."
                )

            # DEFAULT_DOMAIN must not be localhost
            if "localhost" in ds.DEFAULT_DOMAIN or "127.0.0.1" in ds.DEFAULT_DOMAIN:
                raise ImproperlyConfigured(
                    f"DOORMAN['DEFAULT_DOMAIN'] is '{ds.DEFAULT_DOMAIN}'. "
                    "Set it to your production domain (e.g. 'shop.example.com')."
                )
