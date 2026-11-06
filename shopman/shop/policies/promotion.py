"""Decisões puras de promoção, compartilhadas por loja online, PDV, vitrine e concierge.

Este módulo é o ÚNICO lugar que lê os campos de alvo de uma promoção
(``skus``, ``collections``, ``fulfillment_types``, ``customer_segments``,
``birthday_only`` e ``min_order_q``) para decidir se ela vale. Quem consome só
reúne os fatos da compra num ``PromotionContext`` e pergunta a
``promotion_matches``. O gate ``scripts/check_orchestrator_units.py`` reprova
comparação desses campos fora daqui (regra "não reimplementar decisão").

Sem Django, sem banco: a promoção é qualquer objeto com esses atributos (o model
``Promotion`` ou um ``SimpleNamespace`` de teste).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field, replace
from datetime import date
from typing import Any


def promotion_minimum_eligible(
    *,
    min_order_q: int,
    merchandise_subtotal_q: int,
) -> bool:
    """Return whether the merchandise subtotal reaches the promotion minimum.

    A zero minimum keeps the promotion open even for a defensive negative subtotal,
    matching the historical guard that only compared truthy minimums. Callers own the
    adaptation from models or session data to integer monetary quantities.
    """
    minimum_q = int(min_order_q or 0)
    subtotal_q = int(merchandise_subtotal_q or 0)
    return not minimum_q or subtotal_q >= minimum_q


@dataclass(frozen=True)
class Shopper:
    """Quem compra, nos eixos que uma promoção pode exigir.

    O padrão é o visitante anônimo: sem segmento RFM, sem grupo e sem aniversário.
    """

    segment: str = ""
    tier_refs: frozenset[str] = frozenset()
    is_birthday: bool = False

    @staticmethod
    def birthday_on(birthday: date | None, day: date) -> bool:
        """O ``day`` é o aniversário de quem nasceu em ``birthday``?"""
        return birthday is not None and (birthday.month, birthday.day) == (day.month, day.day)


@dataclass(frozen=True)
class PromotionContext:
    """Os fatos da compra no momento da pergunta.

    Cada eixo diz se faz parte da pergunta:

    - ``shopper``: sempre avaliado (padrão: visitante anônimo).
    - ``sku``: ``None`` quando a pergunta não é sobre uma linha (cupom, frete);
      com ``sku``, ``sku_collections`` são as coleções desse item.
    - ``fulfillment_type``: ``None`` quando o atendimento não faz parte da pergunta;
      ``""`` quando o cliente ainda não escolheu (retirada é o padrão da casa);
      senão, o tipo escolhido.
    - ``merchandise_subtotal_q``: ``None`` quando o mínimo não faz parte da pergunta.
    - ``promise_to_any_visitor``: a resposta é uma PROMESSA para qualquer visitante
      (selo da vitrine). Toda condição de compra (atendimento, mínimo) a desfaz,
      porque o visitante ainda não a cumpriu.
    """

    shopper: Shopper = field(default_factory=Shopper)
    sku: str | None = None
    sku_collections: tuple[str, ...] = ()
    fulfillment_type: str | None = None
    merchandise_subtotal_q: int | None = None
    promise_to_any_visitor: bool = False


#: Condições de compra que uma promoção pode deixar de cumprir, na ordem em que
#: ``promotion_unmet_condition`` as confere. É também o motivo que a sacola dá ao
#: cliente para um cupom que ficou sem desconto (``pricing.coupon.reason``).
UNMET_CUSTOMER = "customer"
UNMET_FULFILLMENT = "fulfillment"
UNMET_MINIMUM = "minimum"
UNMET_ITEMS = "items"


def promotion_unmet_condition(promo: Any, ctx: PromotionContext) -> str:
    """A primeira condição desta compra que a promoção não cumpre, ou ``""``.

    ``customer`` (segmento, grupo ou aniversário), ``fulfillment`` (forma de
    recebimento), ``minimum`` (pedido mínimo) ou ``items`` (SKU/coleção da linha).
    ``promotion_matches`` é esta pergunta com resposta sim ou não.
    """
    segments = list(getattr(promo, "customer_segments", None) or [])
    if segments:
        shopper = ctx.shopper
        if shopper.segment not in segments and not shopper.tier_refs.intersection(segments):
            return UNMET_CUSTOMER
    if getattr(promo, "birthday_only", False) and not ctx.shopper.is_birthday:
        return UNMET_CUSTOMER

    fulfillment_types = list(getattr(promo, "fulfillment_types", None) or [])
    if ctx.promise_to_any_visitor:
        if fulfillment_types:
            return UNMET_FULFILLMENT
        if int(getattr(promo, "min_order_q", 0) or 0):
            return UNMET_MINIMUM
    if fulfillment_types and ctx.fulfillment_type is not None:
        chosen = ctx.fulfillment_type.strip()
        if chosen:
            if chosen not in fulfillment_types:
                return UNMET_FULFILLMENT
        elif "pickup" not in fulfillment_types:
            # Sem o tipo escolhido, a promoção que NÃO vale na retirada (só entrega)
            # não pré-aplica: o desconto apareceria e sumiria ao trocar para
            # retirada. A restrita à RETIRADA vale, porque retirada é o padrão da
            # casa até alguém escolher entrega.
            return UNMET_FULFILLMENT

    if ctx.merchandise_subtotal_q is not None and not promotion_minimum_eligible(
        min_order_q=getattr(promo, "min_order_q", 0),
        merchandise_subtotal_q=ctx.merchandise_subtotal_q,
    ):
        return UNMET_MINIMUM

    if ctx.sku is not None:
        skus = list(getattr(promo, "skus", None) or [])
        if skus and ctx.sku not in skus:
            return UNMET_ITEMS
        collections = list(getattr(promo, "collections", None) or [])
        if collections and not any(ref in collections for ref in ctx.sku_collections):
            return UNMET_ITEMS
    return ""


def promotion_minimum_missing_q(promo: Any, merchandise_subtotal_q: int) -> int:
    """Quanto falta (centavos) para a compra chegar ao pedido mínimo da promoção."""
    return max(0, int(getattr(promo, "min_order_q", 0) or 0) - int(merchandise_subtotal_q or 0))


def coupon_zero_reason(
    promo: Any, order_ctx: PromotionContext, line_ctxs: Iterable[PromotionContext]
) -> dict:
    """Por que o cupom ficou na sacola sem descontar nada (beta 06/11).

    O navegador não adivinha: "nenhum item recebe" para um cupom que só esperava o
    pedido mínimo mandava o cliente embora com a sacola errada. ``reason`` é
    ``unavailable`` (vencido, esgotado ou fora do canal), ``customer``,
    ``fulfillment`` (+ ``fulfillment_types``), ``minimum`` (+ ``missing_q``),
    ``items`` (nenhuma linha no alvo) ou ``already_discounted`` (as linhas do alvo
    já têm desconto igual ou maior; o maior ganha, sem somar). ``order_ctx`` é a
    compra inteira (o ``sku`` é ignorado); ``line_ctxs``, uma por linha, sem mínimo.
    """
    if promo is None:
        return {"reason": "unavailable"}
    unmet = promotion_unmet_condition(promo, replace(order_ctx, sku=None))
    if unmet == UNMET_MINIMUM:
        return {"reason": unmet, "missing_q": promotion_minimum_missing_q(promo, order_ctx.merchandise_subtotal_q or 0)}
    if unmet == UNMET_FULFILLMENT:
        return {"reason": unmet, "fulfillment_types": list(getattr(promo, "fulfillment_types", None) or [])}
    if unmet:
        return {"reason": unmet}
    targeted = any(promotion_matches(promo, line_ctx) for line_ctx in line_ctxs)
    return {"reason": "already_discounted" if targeted else UNMET_ITEMS}


def promotion_matches(promo: Any, ctx: PromotionContext) -> bool:
    """A promoção vale para esta compra, nos eixos que ``ctx`` traz?"""
    return not promotion_unmet_condition(promo, ctx)
