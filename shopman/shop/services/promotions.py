"""Consultas de promoção, cupom e geografia de entrega.

Era `adapters/promotion.py`, e não devia ser adapter: adapter existe para **2+
implementações reais** (ADR-001), nunca para contornar uma fronteira que está no lugar
errado. A fronteira era `shop` não poder importar `storefront` — verdade —, mas a causa
estava em `Promotion`/`Coupon`/`DeliveryZone` morarem numa superfície sendo regra de
preço do orquestrador. Com os models de volta em `shop` (ADR-019), o adapter perde a
razão de existir e a chamada volta a ser direta.

O que sobrevive como adapter legítimo é `adapters/audience_sources.py`: `CustomerFavorite`
e `StockAlertSubscription` são dado de superfície de cliente, não regra de preço.
"""

from __future__ import annotations

from typing import Any


def get_active_promotions(now, *, channel_ref: str = "") -> list[Any]:
    """Promoções automáticas ativas (excluindo cupom-only), opcionalmente por canal.

    ``channel_ref`` vazio não filtra — é o chamador que ainda não sabe o canal, não
    "vale em todos". A régua de "vale em todos" é do lado da promoção: M2M vazio
    (mesma semântica de ``RuleConfig.channels``).
    """
    from shopman.shop.models import Promotion

    qs = (
        Promotion.objects.filter(
            is_active=True,
            valid_from__lte=now,
            valid_until__gte=now,
        )
        .exclude(coupons__isnull=False)
        .prefetch_related("channels")
    )
    promotions = list(qs)
    if not channel_ref:
        return promotions
    return [p for p in promotions if p.applies_to_channel(channel_ref)]


def get_coupon_promotion(code: str, now, *, channel_ref: str = "") -> Any | None:
    """A promoção atrelada ao cupom, se válida e alcançável neste canal."""
    from shopman.shop.models import Coupon

    try:
        coupon = (
            Coupon.objects.select_related("promotion")
            .prefetch_related("promotion__channels")
            .get(code=code, is_active=True)
        )
    except Coupon.DoesNotExist:
        return None

    if not coupon.is_available:
        return None

    promo = coupon.promotion
    if not (promo.is_active and promo.valid_from <= now <= promo.valid_until):
        return None
    if channel_ref and not promo.applies_to_channel(channel_ref):
        return None
    return promo


def record_coupon_use(code: str) -> bool:
    """Incrementa o uso do cupom, respeitando ``max_uses`` atomicamente.

    O UPDATE é condicional (``max_uses==0`` ilimitado OU ``uses_count<max_uses``),
    então dois commits concorrentes do mesmo cupom single-use nunca passam do
    teto: o banco serializa e o segundo não incrementa. Retorna True se contou.
    """
    from django.db.models import F, Q

    from shopman.shop.models import Coupon

    updated = Coupon.objects.filter(
        Q(max_uses=0) | Q(uses_count__lt=F("max_uses")),
        code=code,
    ).update(uses_count=F("uses_count") + 1)
    return bool(updated)


def release_coupon_use(code: str) -> None:
    """Devolve um uso do cupom (pedido cancelado/expirado) — nunca abaixo de 0."""
    from django.db.models import F

    from shopman.shop.models import Coupon

    Coupon.objects.filter(code=code, uses_count__gt=0).update(uses_count=F("uses_count") - 1)


def match_delivery_zone(postal_code: str, neighborhood: str) -> Any | None:
    """A DeliveryZone ativa de maior prioridade, ou ``None``."""
    from shopman.shop.models import DeliveryZone

    return DeliveryZone.match(postal_code=postal_code, neighborhood=neighborhood)


def match_distance_band(distance_km: float) -> Any | None:
    """A faixa de distância ativa que cobre ``distance_km``, ou ``None``."""
    from shopman.shop.models import DeliveryDistanceBand

    return DeliveryDistanceBand.match(distance_km)
