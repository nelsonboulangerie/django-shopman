"""Identifiers app config."""

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class IdentifiersConfig(AppConfig):
    name = "shopman.guestman.contrib.identifiers"
    label = "customer_identifiers"
    verbose_name = _("Identificadores")

    def ready(self):
        # O identificador de login sai junto com o contato (A4-1).
        from shopman.guestman.contrib.identifiers import signals

        signals.connect()
