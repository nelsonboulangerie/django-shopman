"""Desconto da Concierge: até o teto da casa, pelo mesmo cupom do site.

Decisão do dono (03/10/2026): "Poderia ter uma configuração de desconto máximo
permitido para a Concierge. Na prática contaria como um cupom de desconto que o
próprio usuário usaria no site. Algo como arredondar um valor até 2%."

O que isto garante, e onde:

- **O teto é do Admin**: ``ChannelConfig.pricing.concierge_discount_max_percent``
  (``Channel.config`` do canal da Concierge, ou ``Shop.defaults``), em % do
  subtotal; padrão 2,5 (aceita decimal), 0 desliga.
- **O valor é do sistema**: ``amount_for`` calcula a partir da sacola; a IA não
  digita número nenhum (regras da casa R1 e R5). A preferência é o arredondamento
  simpático: o total desce até o maior degrau redondo cuja diferença cabe no teto.
- **O caminho é o do site**: um cupom de uso único (``promotions.issue_concierge_coupon``)
  aplicado por ``cart.validate_and_apply_coupon``, as mesmas portas do cupom que o
  cliente digita na loja. Valem canal, pedido mínimo, "maior desconto ganha" e o
  uso contado no commit; nada aqui recalcula preço.
- **Uma vez por pedido**: a sacola guarda ``Session.data["concierge_discount"]``.
- **Auditável**: o cupom se chama ``CONCIERGE-…``, a promoção diz de qual conversa
  veio, e o commit grava o evento ``concierge_discount`` no histórico do pedido
  (``lifecycle._record_coupon_use``), que o Gestor mostra.

Acima do teto, ou quando não dá (teto 0, sem sacola, cupom do cliente já
aplicado), a resposta é a da regra R7: quem decide é a equipe, é só pedir.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import timedelta
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal

from django.db import transaction

logger = logging.getLogger(__name__)

#: Degraus do arredondamento, do mais simpático ao menor (centavos).
ROUND_STEPS_Q = (1000, 500, 100, 50, 10)
#: Quanto tempo o cupom emitido vale. A sacola da conversa fecha bem antes.
COUPON_VALIDITY = timedelta(days=2)
#: ``Session.data`` que marca o desconto já concedido nesta sacola.
SESSION_KEY = "concierge_discount"

GRANTED_COPY_KEY = "CONCIERGE_DISCOUNT_GRANTED"
ABOVE_CAP_COPY_KEY = "CONCIERGE_DISCOUNT_ABOVE_CAP"
ALREADY_GIVEN_COPY_KEY = "CONCIERGE_DISCOUNT_ALREADY_GIVEN"
COUPON_IN_USE_COPY_KEY = "CONCIERGE_DISCOUNT_COUPON_IN_USE"
NO_CART_COPY_KEY = "CONCIERGE_DISCOUNT_NO_CART"

#: "10%", "R$ 5", "5 reais": o cliente pediu um valor, e o que passar do teto é da equipe.
_ASKED_AMOUNT = re.compile(r"\d|\breais\b|\bmetade\b", re.I)


@dataclass(frozen=True)
class Outcome:
    #: ``granted`` · ``already_given`` · ``coupon_in_use`` · ``no_cart`` · ``unavailable``
    code: str
    text: str = ""
    coupon_code: str = ""
    discount_q: int = 0


def _money(value_q: int) -> str:
    from shopman.utils.monetary import format_money

    return f"R$ {format_money(int(value_q))}"


def max_percent(channel_ref: str) -> Decimal:
    """O teto do canal, em % do subtotal (0 = desligado)."""
    from shopman.shop.config import ChannelConfig

    try:
        value = ChannelConfig.for_channel(channel_ref).pricing.concierge_discount_max_percent
    except Exception:
        # Config inválida no Admin: o desconto fica desligado, nunca acima do teto.
        logger.warning("concierge.discount: config unavailable channel=%s", channel_ref, exc_info=True)
        return Decimal(0)
    return max(Decimal(0), Decimal(str(value)))


def cap_q(subtotal_q: int, percent: Decimal) -> int:
    """O desconto máximo, em centavos, arredondado para baixo."""
    if subtotal_q <= 0 or percent <= 0:
        return 0
    return int((Decimal(subtotal_q) * percent / 100).to_integral_value(rounding=ROUND_FLOOR))


def amount_for(*, total_q: int, subtotal_q: int, percent: Decimal) -> int:
    """Quanto a Concierge concede: o arredondamento simpático que cabe no teto.

    O total desce até o maior degrau redondo (R$ 10, 5, 1, 0,50, 0,10) cuja
    diferença cabe no teto: R$ 51,20 com teto de R$ 1,02 vira R$ 51,00. Total já
    redondo, ou nenhum degrau que caiba, desce o maior degrau inteiro que cabe no
    teto. Nunca passa do teto nem do próprio subtotal; 0 quando nada cabe.
    """
    cap = min(cap_q(subtotal_q, percent), max(0, subtotal_q))
    if cap <= 0 or total_q <= 0:
        return 0
    for step in ROUND_STEPS_Q:
        rest = total_q % step
        if 0 < rest <= cap:
            return rest
    for step in ROUND_STEPS_Q:
        if step <= cap:
            return step
    return 0


def min_order_for(discount_q: int, percent: Decimal) -> int:
    """O menor subtotal em que ``discount_q`` ainda cabe no teto (o mínimo do cupom)."""
    if percent <= 0:
        return 0
    value = Decimal(discount_q) * 100 / percent
    return int(value.to_integral_value(rounding=ROUND_CEILING))


def _copy(key: str, **values) -> str:
    from .service import copy_message

    text = copy_message(key)
    for name, value in values.items():
        text = text.replace("{" + name + "}", str(value))
    return text.strip()


def handle_request(*, conversation, channel_ref: str, customer_text: str) -> Outcome:
    """O cliente pediu desconto (regra R7). Concede até o teto, ou diz por que não.

    ``unavailable`` (sem texto) devolve a decisão à frase fixa de R7: teto 0,
    canal desligado, cliente sem identificação comercial, ou o cupom não valeu.
    """
    percent = max_percent(channel_ref)
    if percent <= 0 or not channel_ref:
        return Outcome("unavailable")
    if getattr(conversation, "_channel_off", False) or not getattr(conversation, "_commercial_authority", False):
        return Outcome("unavailable")

    from shopman.shop.services import cart as cart_service

    session = (
        cart_service.get_open_session(session_key=conversation.session_key, channel_ref=channel_ref)
        if conversation.session_key
        else None
    )
    if session is None or not (session.items or []):
        return Outcome("no_cart", _copy(NO_CART_COPY_KEY))
    data = session.data or {}
    if data.get(SESSION_KEY):
        return Outcome("already_given", _copy(ALREADY_GIVEN_COPY_KEY))
    if data.get("coupon_code"):
        # Um cupom por pedido, como no site: o do cliente não é trocado pelo da Concierge.
        return Outcome("coupon_in_use", _copy(COUPON_IN_USE_COPY_KEY))

    return _grant(conversation=conversation, session=session, channel_ref=channel_ref, percent=percent,
                  customer_text=customer_text)


def _grant(*, conversation, session, channel_ref: str, percent: Decimal, customer_text: str) -> Outcome:
    from django.utils import timezone

    from shopman.shop.projections.cart import build_cart
    from shopman.shop.services import cart as cart_service
    from shopman.shop.services import promotions, sessions

    before = build_cart(session.session_key, channel_ref)
    discount_q = amount_for(total_q=int(before.grand_total_q), subtotal_q=int(before.subtotal_q), percent=percent)
    if discount_q <= 0:
        return Outcome("unavailable")

    try:
        with transaction.atomic():
            code = promotions.issue_concierge_coupon(
                value_q=discount_q,
                min_order_q=min_order_for(discount_q, percent),
                channel_ref=channel_ref,
                conversation_id=conversation.pk,
                valid_for=COUPON_VALIDITY,
            )
            applied, _name = cart_service.validate_and_apply_coupon(
                session_key=session.session_key, channel_ref=channel_ref, code=code,
            )
            applied_q = int(((applied.pricing or {}).get("coupon") or {}).get("discount_q") or 0)
            if applied_q <= 0:
                # As portas do cupom recusaram em silêncio (linha já com desconto
                # melhor, por exemplo): nada foi concedido, e nada fica no ar.
                raise _NotApplied
            sessions.modify_session(
                session_key=session.session_key,
                channel_ref=channel_ref,
                ops=[{
                    "op": "set_data",
                    "path": SESSION_KEY,
                    "value": {
                        "coupon_code": code,
                        "discount_q": applied_q,
                        "max_percent": str(percent),
                        "conversation_id": conversation.pk,
                        "at": timezone.now().isoformat(),
                    },
                }],
            )
    except _NotApplied:
        return Outcome("unavailable")
    except Exception:
        logger.warning("concierge.discount: grant failed conversation=%s", conversation.pk, exc_info=True)
        return Outcome("unavailable")

    after = build_cart(session.session_key, channel_ref)
    text = _copy(GRANTED_COPY_KEY, before=_money(before.grand_total_q), after=_money(after.grand_total_q))
    if _ASKED_AMOUNT.search(customer_text or ""):
        text = f"{text}\n{_copy(ABOVE_CAP_COPY_KEY)}".strip()
    return Outcome("granted", text, coupon_code=code, discount_q=applied_q)


class _NotApplied(Exception):
    pass
