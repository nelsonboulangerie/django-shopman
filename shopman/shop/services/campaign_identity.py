"""O link do disparo leva a identidade de quem vai receber.

⚠️ Nasceu de um teste do dono no aparelho dele: mensagem de fornada → botão "Eu quero" →
cardápio → sacola → e o checkout **pediu login**. A pessoa estava dentro do WhatsApp, num
número que nós escolhemos porque sabemos de quem é — e o link jogava essa identidade fora.

O diagnóstico não era "o checkout é paranoico": o checkout exige cliente identificado
(`storefront/presentation/checkout.py::_requires_authentication`), e está certo, porque
telefone é identidade aqui. O defeito era o link da campanha ser o **único** link que a
padaria manda anônimo, num canal onde ela sabe exatamente para quem manda.

A ponte já existia e é usada pelo login por WhatsApp: `/a?t=<token>` → `POST
/api/v1/auth/access/` cria a sessão no host da loja, adota a sacola anônima e leva ao
destino que vem no metadata do token. Aqui só cunhamos um `AccessLink` **por destinatário**
— o envio já é por pessoa (`handlers/campaign.py::_send_to`), então a costura existia.

Três decisões que este módulo carrega:

1. **Prazo = janela do anúncio.** Os 5 minutos padrão do `AccessLink` são do fluxo de
   login, não de uma fornada: quem vê a mensagem 40 minutos depois merece o mesmo caminho.
   Sem janela declarada, vale o teto de `MAX_HOURS` — link de mensagem não pode virar
   crachá permanente.

2. **Sem UUID, link simples.** Assinante anônimo de alerta (só telefone) recebe o link de
   sempre. Não é exceção nem erro: não há identidade a pôr no link.

3. **A cerca não é a `audience`.** Ela existe no model mas ninguém a aplica hoje —
   `exchange_token` nunca passa `required_audience` (`storefront/api/auth.py`). Marcamos
   `WEB_CHECKOUT` como intenção declarada, e quem decide o que a sessão pode fazer é a
   FORÇA da identidade (aparelho conhecido vs. só o número), não este campo.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from django.utils import timezone

logger = logging.getLogger(__name__)

#: Teto do prazo de um link de campanha, quando o anúncio não declara janela. Uma mensagem
#: de WhatsApp fica no aparelho para sempre; o crachá dentro dela, não.
MAX_HOURS = 24


def personal_link(*, customer_uuid: str, destination: str, announcement=None) -> str:
    """Link pessoal para este destinatário, ou ``""`` quando não há como personalizar.

    Devolver vazio (em vez de levantar) é deliberado: o chamador cai no link comum, e uma
    campanha nunca deixa de sair porque a identidade não pôde ser cunhada.
    """
    if not customer_uuid or not destination.startswith("/"):
        return ""
    try:
        from shopman.doorman.models import AccessLink

        from shopman.shop.services import storefront_links

        _link, raw_token = AccessLink.create_with_token(
            customer_id=customer_uuid,
            audience=AccessLink.Audience.WEB_CHECKOUT,
            source=AccessLink.Source.INTERNAL,
            expires_at=link_expiry(announcement),
            metadata={
                # `next` é o que `_access_link_redirect` lê para decidir o destino. O
                # destino mora no TOKEN, nunca num parâmetro da URL — é o que impede o
                # link de virar redirect aberto.
                "next": destination,
                #: De onde veio esta identidade. É este marcador que a loja vai ler para
                #: saber que conhecemos o NÚMERO e não necessariamente as MÃOS.
                "login_source": "campaign",
                "announcement": getattr(announcement, "pk", None),
            },
        )
    except Exception:
        # Falhar aqui não pode calar a campanha: sem link pessoal, sai o link comum.
        logger.warning("campaign.personal_link_failed", exc_info=True)
        return ""

    base = storefront_links.storefront_url(storefront_links.path_access())
    return f"{base}?t={raw_token}"


def link_expiry(announcement=None):
    """Quando o link morre: a janela do anúncio, com teto de ``MAX_HOURS``.

    O anúncio que não expira (`expires_after_minutes = 0`) não ganha link eterno — o teto
    existe justamente para o caso em que ninguém declarou nada.
    """
    ceiling = timezone.now() + timedelta(hours=MAX_HOURS)
    window = getattr(announcement, "expires_at", None)
    if window is None:
        return ceiling
    return min(window, ceiling)
