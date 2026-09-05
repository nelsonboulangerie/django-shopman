"""Integrações — a tela que responde "isto está mesmo de pé?".

## Por que esta projeção existe

A casa **já sabia** responder. `build_provider_readiness` cobre Focus, Efí,
Stripe e a cadeia de entrega do OTP, e existe desde antes. Só que os dois
únicos consumidores eram:

- a projeção do PDV, que carrega `provider_readiness` no payload — e **nenhum
  componente do app renderiza**; e
- o comando `smoke_gateways`, que exige o console da DigitalOcean — e o console
  **não recebe as variáveis marcadas SECRET**, então toda credencial chega
  vazia e o comando reprova por um motivo falso.

Ou seja: a resposta existia e nenhum humano conseguia fazer a pergunta. Esta
projeção é a ponte que faltava.

## O que ela NÃO faz

Não confunde **configurado** com **funciona**. Prontidão lê settings: diz que a
chave está lá, não que o provedor aceita. Para a diferença entre as duas, existe
o botão de teste de e-mail — o único jeito de saber se a porta de saída abre é
tentar sair por ela.

Nada aqui devolve segredo. Host, porta, usuário e remetente são identificação;
senha e token nunca entram no contexto do template.
"""

from __future__ import annotations

from dataclasses import dataclass

from django.conf import settings

from shopman.backstage.services.integration_readiness import build_provider_readiness
from shopman.shop.adapters import notification_email
from shopman.shop.environment import environment_name, is_production


@dataclass(frozen=True)
class EmailChannelProjection:
    """O estado do canal de e-mail, em linguagem de gestor."""

    #: `True` quando a cadeia de notificação vai realmente tentar este canal.
    entrega: bool
    backend: str
    host: str
    port: int
    use_tls: bool
    user: str
    sender: str
    #: `True` se há senha configurada — o VALOR nunca sai daqui.
    has_password: bool
    timeout_seconds: int
    motivo: str


@dataclass(frozen=True)
class DiagnosticsProjection:
    environment: str
    is_production: bool
    providers: tuple[dict, ...]
    email: EmailChannelProjection


def _email_projection() -> EmailChannelProjection:
    backend = str(getattr(settings, "EMAIL_BACKEND", "") or "")
    host = str(getattr(settings, "EMAIL_HOST", "") or "")
    sender = str(getattr(settings, "DEFAULT_FROM_EMAIL", "") or "")
    entrega = notification_email.is_available()

    if entrega:
        motivo = "O canal entrega: a cadeia de notificação vai tentar por aqui."
    elif not backend:
        motivo = "Sem EMAIL_BACKEND: nenhum e-mail sai."
    elif "smtp" in backend.lower() and not host:
        motivo = "Backend SMTP sem EMAIL_HOST: a primeira conexão falharia."
    elif any(inerte in backend.lower() for inerte in ("console", "locmem", "dummy")):
        # Antes do remetente, de propósito: com backend inerte o remetente nem
        # chega a importar, e culpá-lo mandaria o operador consertar a coisa errada.
        motivo = (
            "Backend inerte (console/locmem/dummy): imprime no log e diz que "
            "entregou. A cadeia pula este canal de propósito."
        )
    elif not notification_email.remetente_entrega(sender):
        # O SMTP está de pé e mesmo assim não entrega: quem não existe é o
        # REMETENTE. `.local` (RFC 6762) e `example.*` (RFC 2606) não têm DNS
        # público, logo não têm SPF nem DMARC. Sem este ramo a tela diria
        # "backend inerte" para um SMTP configurado — mandando o operador
        # conferir exatamente o lugar onde não está o problema.
        motivo = (
            f"Remetente {sender or '(vazio)'} não sai da casa: domínio reservado ou "
            "ausente, sem SPF nem DMARC possíveis. Defina DEFAULT_FROM_EMAIL com um "
            "domínio real; até lá a cadeia segue para SMS e WhatsApp."
        )
    else:
        motivo = "O canal não entrega, e a causa não está em backend, host nem remetente."

    return EmailChannelProjection(
        entrega=entrega,
        backend=backend,
        host=host,
        port=int(getattr(settings, "EMAIL_PORT", 0) or 0),
        use_tls=bool(getattr(settings, "EMAIL_USE_TLS", False)),
        user=str(getattr(settings, "EMAIL_HOST_USER", "") or ""),
        sender=sender,
        has_password=bool(str(getattr(settings, "EMAIL_HOST_PASSWORD", "") or "").strip()),
        timeout_seconds=int(getattr(settings, "EMAIL_TIMEOUT", 0) or 0),
        motivo=motivo,
    )


def build_diagnostics() -> DiagnosticsProjection:
    """Prontidão das integrações + o estado do canal de e-mail."""
    return DiagnosticsProjection(
        environment=environment_name(),
        is_production=is_production(),
        providers=tuple(item.as_projection() for item in build_provider_readiness(mode="runtime")),
        email=_email_projection(),
    )


__all__ = ["EmailChannelProjection", "DiagnosticsProjection", "build_diagnostics"]
