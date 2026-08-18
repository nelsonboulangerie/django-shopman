from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class CashmanConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "shopman.cashman"
    label = "cashman"
    verbose_name = _("Caixa")
