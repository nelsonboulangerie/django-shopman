"""Cada plataforma está pronta para entregar? E se não, por quê — ANTES de publicar.

Nasceu de uma correção do dono: a primeira versão disto só sabia falar de WhatsApp,
porque foi escrita durante um teste de WhatsApp. Anúncio não é mensagem de um canal — é
conteúdo que sai por vários, e **cada um tem exigência própria**.

## Dois tipos de entrega, não um

A TV **não** está aqui, e não é esquecimento: ela mostra a promoção porque a promoção vale
naquele canal, não porque um anúncio a escolheu como destino (ADR-020 §10).

O erro de projetar em volta de um canal é achar que "enviar" quer dizer a mesma coisa em
todos. Não quer:

· **publicação** (`instagram`, `facebook`, `google_business`) — UMA peça publicada na
  plataforma. Não tem destinatário, não tem janela de 24h, não tem consentimento. Precisa
  de credencial e de um adapter que fale a API deles.
· **mensagem direta** (`whatsapp`) — UMA mensagem POR PESSOA. Tem consentimento, tem
  janela de 24h, e exige template aprovado para sair dela.

O formato do relato é **genérico** (pronta? por quê não? o que fazer?) e a **razão** é
específica de cada plataforma. Era isso que faltava: genérico onde dá, específico onde
precisa.

## Por que antes e não depois

Hoje o Instagram só revela que não tem adapter DEPOIS de você aprovar: o anúncio vira
`pending_manual` e alguém descobre no painel que nada foi publicado. Saber disso antes é
a diferença entre escolher plataforma com informação e escolher no escuro.
"""

from __future__ import annotations

from dataclasses import dataclass

#: Publicação: uma peça na plataforma, sem destinatário.
PUBLICATION = "publication"
#: Mensagem direta: uma mensagem por pessoa, com consentimento e janela.
DIRECT_MESSAGE = "direct_message"

PLATFORM_KIND: dict[str, str] = {
    "instagram": PUBLICATION,
    "facebook": PUBLICATION,
    "google_business": PUBLICATION,
    "whatsapp": DIRECT_MESSAGE,
}


@dataclass(frozen=True)
class PlatformReadiness:
    """Uma plataforma e o que falta nela.

    ``ready=False`` é bloqueio: nada sai. ``limitation`` é o meio-termo honesto — sai,
    mas não para todo mundo —, e ele merece existir porque "funciona" e "funciona para
    quem você imagina" não são a mesma coisa.
    """

    platform: str
    kind: str
    ready: bool
    reason: str = ""
    action: str = ""
    limitation: str = ""


def readiness_for(platforms) -> tuple[PlatformReadiness, ...]:
    """O estado de entrega de cada plataforma pedida, na ordem em que vieram."""
    out = []
    for platform in platforms or []:
        kind = PLATFORM_KIND.get(platform)
        if kind is None:
            out.append(
                PlatformReadiness(
                    platform=platform,
                    kind="unknown",
                    ready=False,
                    reason="Plataforma desconhecida pelo sistema.",
                    action="Revisar as plataformas da campanha",
                )
            )
        elif kind == PUBLICATION:
            out.append(_publication_readiness(platform))
        elif kind == DIRECT_MESSAGE:
            out.append(_direct_message_readiness(platform))
        else:
            out.append(PlatformReadiness(platform=platform, kind=kind, ready=True))
    return tuple(out)


def _publication_readiness(platform: str) -> PlatformReadiness:
    """Publicação depende de adapter + credencial da plataforma. Nada de janela."""
    from shopman.shop.handlers.campaign import _posting_adapter

    adapter = _posting_adapter(platform)
    if adapter is None:
        return PlatformReadiness(
            platform=platform,
            kind=PUBLICATION,
            ready=False,
            reason="Não há integração de publicação configurada para esta plataforma.",
            action="Configurar as credenciais da plataforma",
        )

    probe = getattr(adapter, "is_available", None)
    if probe is not None and not probe():
        return PlatformReadiness(
            platform=platform,
            kind=PUBLICATION,
            ready=False,
            reason="A integração existe, mas está sem credencial neste ambiente.",
            action="Conferir as credenciais da plataforma",
        )

    return PlatformReadiness(platform=platform, kind=PUBLICATION, ready=True)


def _direct_message_readiness(platform: str) -> PlatformReadiness:
    """Mensagem direta depende de transporte E, para sair da janela, de template."""
    from shopman.shop.handlers.campaign import _whatsapp_backend

    if _whatsapp_backend() is None:
        return PlatformReadiness(
            platform=platform,
            kind=DIRECT_MESSAGE,
            ready=False,
            reason="Nenhum transporte configurado — o envio falharia para todos.",
            action="Conferir a credencial do canal neste ambiente",
        )

    if not _has_approved_template():
        return PlatformReadiness(
            platform=platform,
            kind=DIRECT_MESSAGE,
            ready=True,
            limitation=(
                "Só alcança quem conversou com a loja nas últimas 24 horas. Quem não "
                "conversou não recebe — é regra da plataforma, não falha do envio."
            ),
            action="Escolher o template aprovado para o anúncio",
        )

    return PlatformReadiness(platform=platform, kind=DIRECT_MESSAGE, ready=True)


def _has_approved_template(event: str = "announcement_published") -> bool:
    from shopman.shop.models import NotificationTemplate

    return (
        NotificationTemplate.objects.filter(event=event)
        .exclude(whatsapp_flow_ns="")
        .exists()
    )
