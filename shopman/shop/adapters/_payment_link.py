"""Validade do LINK de pagamento — um relógio só, escrito nos dois lados.

O link é a cobrança do pedido remoto: o balcão anota, o cliente paga depois, do
celular. Enquanto nenhum prazo era gravado, existia um relógio — o do Stripe,
que expira a sessão hospedada em 24 h por conta própria — e ninguém aqui o lia:
o pedido ficava aberto, o estoque preso, e o cliente descobria que "o link
parou de funcionar" ligando para a padaria.

Aqui mora o único cálculo do prazo. Todo adapter que emite link (Stripe, mock)
o usa para as DUAS gravações: ``PaymentIntent.expires_at`` (que agenda a
Directive ``payment.timeout`` e aparece na tela do PDV como "vale até …") e o
``expires_at`` mandado ao gateway. Dois relógios era exatamente o problema.

O botão é ``SHOPMAN_PAYMENT_LINK_TTL_HOURS`` (default 24). O Stripe aceita de
30 min a 24 h, então o valor é preso a essa régua aqui — uma env fora da faixa
não pode derrubar o ``Session.create`` com o cliente na frente do balcão.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from django.conf import settings
from django.utils import timezone

DEFAULT_LINK_TTL_HOURS = 24

#: Piso do Stripe: 30 minutos.
LINK_TTL_MIN = timedelta(minutes=30)
#: Teto do Stripe: 24 horas — menos um minuto de folga. O Stripe confere
#: ``expires_at`` contra o relógio DELE ao receber a chamada; um servidor nosso
#: alguns segundos adiantado mandaria "24 h e 3 s" e a sessão seria recusada.
#: O minuto não muda o que a tela diz ("amanhã às 9h") nem o que o pedido
#: espera; só garante que o mesmo instante caiba nos dois lados.
LINK_TTL_MAX = timedelta(hours=24) - timedelta(minutes=1)


def link_ttl() -> timedelta:
    """Quanto tempo o link vale, já preso à régua do gateway."""
    raw = getattr(settings, "SHOPMAN_PAYMENT_LINK_TTL_HOURS", DEFAULT_LINK_TTL_HOURS)
    try:
        hours = float(raw)
    except (TypeError, ValueError):
        hours = float(DEFAULT_LINK_TTL_HOURS)
    ttl = timedelta(hours=hours)
    return max(LINK_TTL_MIN, min(ttl, LINK_TTL_MAX))


def link_expires_at(now: datetime | None = None) -> datetime:
    """O instante em que o link vence — o MESMO para o Payman e para o gateway."""
    return (now or timezone.now()) + link_ttl()


def link_expires_at_epoch(expires_at: datetime) -> int:
    """O mesmo instante no vocabulário do Stripe (``expires_at`` em epoch, segundos)."""
    return int(expires_at.timestamp())
