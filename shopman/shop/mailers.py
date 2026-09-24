"""O que está configurado em ``MAILERS``, em forma legível.

O Django 6.1 deprecou todos os ``EMAIL_*`` e o Django 7 os remove. Quem fica é
``MAILERS`` — um dicionário por alias, com ``BACKEND`` e ``OPTIONS``. Este
módulo é o ÚNICO lugar da casa que lê esse dicionário, e existe porque ler à
mão erra de três formas, todas caladas:

* **``OPTIONS`` é opcional — e o ambiente de teste APAGA.** O
  ``setup_test_environment()`` do Django reescreve todo alias para
  ``{"BACKEND": locmem}``, sem ``OPTIONS``. Quem escrever
  ``settings.MAILERS["default"]["OPTIONS"]["host"]`` levanta ``KeyError`` na
  suíte e em lugar nenhum além dela.
* **``BACKEND`` também é opcional, e o default NÃO é o de console.** Quando a
  entrada não declara ``BACKEND``, o Django usa SMTP
  (``DEFAULT_MAILER_BACKEND``, em ``django/core/mail/handler.py``).
* **Não dá mais para perguntar ao ``settings``.** Com ``MAILERS`` definido,
  ``settings.EMAIL_BACKEND`` levanta ``AttributeError``
  (``django/conf/__init__.py``) — então um ``getattr(settings,
  "EMAIL_BACKEND", "")`` que sobrevivesse ao rename passaria a devolver o
  default, calado. Esse é exatamente o fail-open que o ``is_available()`` do
  e-mail existe para fechar: canal inerte que se declara disponível
  curto-circuita a cadeia antes do SMS e do WhatsApp.

A SENHA não entra aqui, só o fato de existir. Quem precisa do valor é o
backend do Django, e ele o lê do próprio ``MAILERS``.
"""

from __future__ import annotations

from dataclasses import dataclass

from django.conf import settings
from django.core.mail import DEFAULT_MAILER_ALIAS

#: O que o Django assume quando a entrada de ``MAILERS`` não declara
#: ``BACKEND``. É SMTP, não o de console — ver ``DEFAULT_MAILER_BACKEND``.
_BACKEND_PADRAO_DO_DJANGO = "django.core.mail.backends.smtp.EmailBackend"

#: Alias do mesmo servidor com teto de espera curto, para o botão "testar
#: envio" do Admin. Mora aqui para que a view e o ``config/settings.py`` não
#: combinem a string por coincidência.
DIAGNOSTICS_ALIAS = "diagnostics"


@dataclass(frozen=True)
class MailerConfig:
    """A entrada ``default`` de ``MAILERS``, resolvida e com defaults aplicados."""

    backend: str
    host: str
    port: int
    use_tls: bool
    username: str
    #: `True` se há senha configurada — o VALOR nunca sai daqui.
    has_password: bool
    timeout_seconds: int


def default_mailer() -> MailerConfig:
    """A configuração do alias ``default``.

    Sem entrada ``default`` o resultado é "SMTP sem host", que é o estado
    fail-closed correto: ``notification_email.is_available()`` devolve ``False``
    e a cadeia de notificação segue para SMS e WhatsApp. Um default de console
    aqui seria pior — diria "entrega" para um canal que só imprime no log.
    """
    mailers = getattr(settings, "MAILERS", None) or {}
    entrada = dict(mailers.get(DEFAULT_MAILER_ALIAS) or {})
    options = dict(entrada.get("OPTIONS") or {})

    return MailerConfig(
        backend=str(entrada.get("BACKEND") or _BACKEND_PADRAO_DO_DJANGO),
        host=str(options.get("host") or ""),
        port=int(options.get("port") or 0),
        use_tls=bool(options.get("use_tls") or False),
        username=str(options.get("username") or ""),
        has_password=bool(str(options.get("password") or "").strip()),
        timeout_seconds=int(options.get("timeout") or 0),
    )


__all__ = ["DIAGNOSTICS_ALIAS", "MailerConfig", "default_mailer"]
