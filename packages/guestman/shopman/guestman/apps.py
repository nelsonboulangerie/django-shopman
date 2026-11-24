from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class GuestmanConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "shopman.guestman"
    label = "guestman"
    verbose_name = _("Clientes")

    def ready(self):
        self._register_ref_types()
        # O número que sai de um cadastro avisa (``contact_reassigned``) por qualquer
        # caminho que apague o contato.
        from shopman.guestman.services import identity

        identity.connect_signals()

    def _register_ref_types(self):
        try:
            from shopman.refs import register_ref_type
            from shopman.refs.types import RefType
            customer = RefType(
                slug="CUSTOMER",
                label="Cliente",
                allowed_targets=("guestman.Customer",),
                unique_scope="all",
                normalizer="upper_strip",
            )
            try:
                register_ref_type(customer)
            except ValueError:
                pass
        except ImportError:
            pass
