from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class CashmanAdminUnfoldConfig(AppConfig):
    name = "shopman.cashman.contrib.admin_unfold"
    label = "cashman_admin_unfold"
    verbose_name = _("Admin (Unfold)")
