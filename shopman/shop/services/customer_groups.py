"""Dono único da configuração comercial de um grupo de clientes.

Admin e Gestor passam por esta porta para manter ``PriceTier`` e sua promoção
``grupo-<ref>`` atomicamente. A faixa continua sendo do Guestman; a promoção,
do orquestrador. Este serviço é a costura explícita entre os dois domínios.
"""

from __future__ import annotations

from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal

from django.utils import timezone

from shopman.shop.models import Channel, Promotion
from shopman.shop.services import promotions as promotion_service

GROUP_DISCOUNT_OPEN_END = datetime(2099, 12, 31, 23, 59, 59)
NO_DISCOUNT = ""

#: Os tipos de vantagem que um grupo pode carregar, na ordem em que o gestor lê.
#: Espelha ``guestman.PriceTierAdvantage.Kind``: o desconto e a lista de preço NÃO
#: entram aqui porque já têm dono canônico (a ``Promotion`` ``grupo-<ref>`` e
#: ``PriceTier.listing_ref``).
ADVANTAGE_KINDS: tuple[str, ...] = (
    "free_shipping",
    "exclusive_collections",
    "exclusive_notifications",
)


def group_promotion(tier_ref: str) -> Promotion | None:
    if not tier_ref:
        return None
    return Promotion.objects.filter(ref=promotion_service.group_discount_ref(tier_ref)).first()


def metadata_with_group_settings(
    metadata: dict,
    *,
    discount_kind: str = "",
    rounding: bool = True,
    savings_message: str = "",
) -> dict:
    merged = dict(metadata or {})
    kind = str(discount_kind or "").strip()
    if kind:
        merged["discount_kind"] = kind
    else:
        merged.pop("discount_kind", None)
    merged["rounding"] = 50 if rounding else 0
    savings = str(savings_message or "").strip()
    if savings:
        merged["savings_message"] = savings
    else:
        merged.pop("savings_message", None)
    return merged


def sync_group_advantages(tier, advantages) -> None:
    """Grava as vantagens tipadas do grupo: uma linha por TIPO, e nunca apaga.

    ``advantages`` é o conjunto que o formulário mandou, com ``kind``, ``priority``,
    ``is_active`` e ``config`` já tipados. Tipo ausente do conjunto não é tocado; tipo
    presente fica desligado em vez de sumir, porque o grupo é histórico e "esta vantagem
    não vale mais" não é a mesma coisa que "esta vantagem nunca existiu". O
    ``UniqueConstraint(tier, kind)`` garante a linha única por tipo.
    """
    from shopman.guestman.models import PriceTierAdvantage

    existing = {advantage.kind: advantage for advantage in tier.advantages.all()}
    for values in advantages:
        advantage = existing.get(values["kind"])
        if advantage is None:
            advantage = PriceTierAdvantage(tier=tier, kind=values["kind"])
        advantage.priority = values["priority"]
        advantage.is_active = values["is_active"]
        advantage.config = values["config"]
        advantage.full_clean()
        advantage.save()


def discount_value_q(kind: str, value: Decimal) -> int:
    if kind == Promotion.PERCENT:
        return int(value)
    return int((value * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def sync_group_discount(
    tier,
    *,
    discount_type: str,
    discount_value_q: int = 0,
    channel_refs: list[str] | tuple[str, ...] = (),
    pickup_only: bool = False,
    previous_ref: str = "",
) -> Promotion | None:
    """Cria, atualiza ou pausa a promoção derivada do grupo.

    ``channel_refs`` vazio significa todos os canais, como no modelo Promotion.
    A promoção nunca é apagada: pedidos históricos continuam explicáveis.
    """
    promo = group_promotion(previous_ref or tier.ref)
    if not discount_type:
        if promo is not None and promo.is_active:
            promo.is_active = False
            promo.save(update_fields=["is_active"])
        return promo
    if promo is None:
        promo = Promotion(valid_from=timezone.now())
    promo.ref = promotion_service.group_discount_ref(tier.ref)
    promo.name = tier.name
    promo.type = discount_type
    promo.value = int(discount_value_q)
    promo.customer_segments = [tier.ref]
    promo.birthday_only = False
    promo.valid_until = timezone.make_aware(GROUP_DISCOUNT_OPEN_END)
    if promo.valid_from > timezone.now():
        promo.valid_from = timezone.now()
    promo.is_active = True
    promo.fulfillment_types = ["pickup"] if pickup_only else []
    promo.full_clean(exclude={"channels"})
    promo.save()
    promo.channels.set(Channel.objects.filter(ref__in=channel_refs))
    return promo
