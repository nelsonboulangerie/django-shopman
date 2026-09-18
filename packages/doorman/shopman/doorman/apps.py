import logging

from django.apps import AppConfig
from django.core.exceptions import ImproperlyConfigured
from django.utils.translation import gettext_lazy as _

logger = logging.getLogger("shopman.doorman")


def enforce_production_settings(ds) -> None:
    """Recusa subir com configuração de acesso que não serve fora de DEBUG.

    Mora fora do ``ready()`` de propósito: uma trava que só pode ser exercida
    subindo um processo inteiro não tem teste, e esta não tinha nenhum — foi
    por isso que ela passou semanas conhecendo só metade do problema.
    """
    if not ds.ACCESS_LINK_API_KEY:
        raise ImproperlyConfigured(
            "DOORMAN['ACCESS_LINK_API_KEY'] must be set in production. "
            "The access link creation endpoint would be unauthenticated. "
            "Set a strong random key, or if you intentionally don't use "
            "access link creation, set DOORMAN['ACCESS_LINK_API_KEY'] "
            "to any non-empty value."
        )

    # Um sender que REVELA o código não pode rodar em produção.
    #
    # ⚠️ Esta trava comparava o NOME exato (`== "…ConsoleSender"`) e por isso
    # conhecia só um dos dois irmãos. O `LogSender` loga o código em claro do
    # mesmo jeito e passava batido — e é justamente ele que os dois specs da DO
    # declaravam em `DOORMAN_MESSAGE_SENDER_CLASS`. Bastava alguém esvaziar
    # `SHOPMAN_OTP_DELIVERY_CHAIN` para contornar uma queda da Comtele (a
    # primeira coisa que se tenta) e o código de login de todo cliente passaria
    # a sair no log de produção, com a trava calada. P1 do laudo de 01/09.
    #
    # Agora a pergunta é de CAPABILITY (`reveals_code`), não de nome, e um teste
    # de varredura obriga todo sender novo do módulo a respondê-la.
    #
    # A importação do sender fica DENTRO da condição de cadeia vazia: é o único
    # caso que precisa ser julgado, e assim o boot não carrega módulo de
    # provedor à toa durante o `ready()`.
    if not ds.DELIVERY_CHAIN:
        from .senders import sender_reveals_code

        if sender_reveals_code(ds.MESSAGE_SENDER_CLASS):
            raise ImproperlyConfigured(
                f"DOORMAN['MESSAGE_SENDER_CLASS'] is set to "
                f"{ds.MESSAGE_SENDER_CLASS}, which REVEALS the OTP code "
                "(prints or logs it) instead of delivering it to the customer. "
                "With DOORMAN['DELIVERY_CHAIN'] empty it becomes the only "
                "sender, so every customer's login code would be written to "
                "the production log. Configure a real sender (WhatsApp, SMS, "
                "Email) or set DOORMAN['DELIVERY_CHAIN']."
            )

    if "localhost" in ds.DEFAULT_DOMAIN or "127.0.0.1" in ds.DEFAULT_DOMAIN:
        raise ImproperlyConfigured(
            f"DOORMAN['DEFAULT_DOMAIN'] is '{ds.DEFAULT_DOMAIN}'. "
            "Set it to your production domain (e.g. 'shop.example.com')."
        )


class DoormanConfig(AppConfig):
    name = "shopman.doorman"
    label = "doorman"
    verbose_name = _("Gestão do acesso")
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        from django.conf import settings

        from . import signals  # noqa: F401
        from .conf import get_doorman_settings

        if not settings.DEBUG:
            enforce_production_settings(get_doorman_settings())
