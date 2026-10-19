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

from dataclasses import dataclass, field
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


def promotion_matches(promo: Any, ctx: PromotionContext) -> bool:
    """A promoção vale para esta compra, nos eixos que ``ctx`` traz?"""
    segments = list(getattr(promo, "customer_segments", None) or [])
    if segments:
        shopper = ctx.shopper
        if shopper.segment not in segments and not shopper.tier_refs.intersection(segments):
            return False
    if getattr(promo, "birthday_only", False) and not ctx.shopper.is_birthday:
        return False

    fulfillment_types = list(getattr(promo, "fulfillment_types", None) or [])
    if ctx.promise_to_any_visitor:
        if fulfillment_types or int(getattr(promo, "min_order_q", 0) or 0):
            return False
    if fulfillment_types and ctx.fulfillment_type is not None:
        chosen = ctx.fulfillment_type.strip()
        if chosen:
            if chosen not in fulfillment_types:
                return False
        elif "pickup" not in fulfillment_types:
            # Sem o tipo escolhido, a promoção que NÃO vale na retirada (só entrega)
            # não pré-aplica: o desconto apareceria e sumiria ao trocar para
            # retirada. A restrita à RETIRADA vale, porque retirada é o padrão da
            # casa até alguém escolher entrega.
            return False

    if ctx.merchandise_subtotal_q is not None and not promotion_minimum_eligible(
        min_order_q=getattr(promo, "min_order_q", 0),
        merchandise_subtotal_q=ctx.merchandise_subtotal_q,
    ):
        return False

    if ctx.sku is not None:
        skus = list(getattr(promo, "skus", None) or [])
        if skus and ctx.sku not in skus:
            return False
        collections = list(getattr(promo, "collections", None) or [])
        if collections and not any(ref in collections for ref in ctx.sku_collections):
            return False
    return True
