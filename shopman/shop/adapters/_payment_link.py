"""Validade do LINK de pagamento — um relógio só, escrito nos dois lados.

O link é a cobrança do pedido remoto: o balcão anota, o cliente paga depois, do
celular. Enquanto nenhum prazo era gravado, existia um relógio — o do Stripe,
que expira a sessão hospedada em 24 h por conta própria — e ninguém aqui o lia:
o pedido ficava aberto, o estoque preso, e o cliente descobria que "o link
parou de funcionar" ligando para a padaria.

Aqui mora o único cálculo do prazo. Todo adapter que emite link (Stripe, mock)
o usa para as DUAS gravações: ``PaymentIntent.expires_at`` (que agenda a
Directive ``payment.timeout`` e aparece na tela do PDV como "pague até …") e o
``expires_at`` mandado ao gateway. Dois relógios era exatamente o problema.

## A regra

``vence = min(agora + janela, corte do atendimento)``, preso à régua do Stripe.

- **janela** é configuração do CANAL (``ChannelConfig.payment.link_timeout_minutes``,
  default 120) e chega ao adapter em ``config["link_timeout_minutes"]``. É o
  teto: um link de 24 h segurava estoque por um dia inteiro para um pão que é
  para hoje ou para amanhã.
- **corte do atendimento** é o instante em que o pedido precisa estar pago para
  a casa cumprir — o início da janela combinada de retirada/entrega ou o
  fechamento da loja no dia do compromisso. Quem o calcula é
  ``services/payment_deadline`` (conhece pedido e calendário); ao adapter ele
  chega pronto, em ``config["link_expires_by"]`` (ISO), para o adapter não ter
  que conhecer pedido.
- **a régua do Stripe** fica por cima: piso de 30 min e teto de 24 h − 1 min.
  Corte já passado ou a menos de 30 min vale o piso — a casa aceita esse caso
  raro (venda de link às 17h50 para retirar às 18h), porque a alternativa era o
  ``Session.create`` cair com o cliente na frente do balcão.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from django.utils import timezone

logger = logging.getLogger(__name__)

#: Piso do Stripe: 30 minutos.
LINK_TTL_MIN = timedelta(minutes=30)
#: Teto do Stripe: 24 horas — menos um minuto de folga. O Stripe confere
#: ``expires_at`` contra o relógio DELE ao receber a chamada; um servidor nosso
#: alguns segundos adiantado mandaria "24 h e 3 s" e a sessão seria recusada.
LINK_TTL_MAX = timedelta(hours=24) - timedelta(minutes=1)


def default_link_timeout() -> timedelta:
    """A janela quando o canal não diz nada — o default da própria ``ChannelConfig``.

    Uma fonte só para o número: o adapter chamado sem configuração (o
    ``_adapter_config`` falhou ao resolver o canal) vence no mesmo prazo que um
    canal recém-criado no Admin.
    """
    from shopman.shop.config import ChannelConfig

    return timedelta(minutes=ChannelConfig.Payment.link_timeout_minutes)


def link_window(timeout_minutes) -> timedelta:
    """Quanto tempo o link vale contado de agora, antes do corte e da régua."""
    try:
        minutes = float(timeout_minutes)
    except (TypeError, ValueError):
        return default_link_timeout()
    if minutes <= 0:
        return default_link_timeout()
    return timedelta(minutes=minutes)


def parse_expires_by(raw) -> datetime | None:
    """O corte do atendimento como chegou no config (ISO ou datetime), ou ``None``."""
    if raw is None or raw == "":
        return None
    if isinstance(raw, datetime):
        value = raw
    else:
        try:
            value = datetime.fromisoformat(str(raw))
        except ValueError:
            logger.debug("payment_link: link_expires_by ilegível: %r", raw)
            return None
    if not timezone.is_aware(value):
        value = timezone.make_aware(value)
    return value


def link_expires_at(
    now: datetime | None = None,
    *,
    timeout_minutes=None,
    expires_by=None,
) -> datetime:
    """O instante em que o link vence — o MESMO para o Payman e para o gateway.

    ``min(now + janela, corte)``, preso a ``[now + 30 min, now + 24 h − 1 min]``.
    """
    now = now or timezone.now()
    expires_at = now + link_window(timeout_minutes)
    cutoff = parse_expires_by(expires_by)
    if cutoff is not None and cutoff < expires_at:
        expires_at = cutoff
    return max(now + LINK_TTL_MIN, min(expires_at, now + LINK_TTL_MAX))


def link_expires_at_epoch(expires_at: datetime) -> int:
    """O mesmo instante no vocabulário do Stripe (``expires_at`` em epoch, segundos)."""
    return int(expires_at.timestamp())
