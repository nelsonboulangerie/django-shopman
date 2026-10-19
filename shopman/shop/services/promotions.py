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

from dataclasses import dataclass
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


#: O prefixo do ``Promotion.ref`` do desconto de um grupo de clientes (``PriceTier``).
#: Um grupo tem UM desconto automático; o ref deriva do grupo para o Admin achar a
#: promoção que edita sem guardar ponteiro em lugar nenhum.
GROUP_DISCOUNT_REF_PREFIX = "grupo-"

#: Tipos de vantagem resolvidos pelo motor. `discount` e `price_list` têm dono canônico
#: (a `Promotion` `grupo-<ref>` e `PriceTier.listing_ref`); os demais vivem em
#: `PriceTierAdvantage`.
ADVANTAGE_KINDS = (
    "discount",
    "price_list",
    "free_shipping",
    "exclusive_collections",
    "exclusive_notifications",
)


def group_discount_ref(price_tier_ref: str) -> str:
    return f"{GROUP_DISCOUNT_REF_PREFIX}{price_tier_ref}"


@dataclass(frozen=True)
class GroupAdvantage:
    """A melhor vantagem de um TIPO entre os grupos do cliente. Uma só, sem acumular."""

    kind: str
    tier_ref: str
    label: str
    value: Any


def _tier_refs(price_tier_refs) -> list[str]:
    """Normaliza um ref, uma lista ou um queryset na lista de grupos do cliente."""
    if not price_tier_refs:
        return []
    raw = [price_tier_refs] if isinstance(price_tier_refs, str) else list(price_tier_refs)
    refs: list[str] = []
    for item in raw:
        ref = str(item or "").strip()
        if ref and ref not in refs:
            refs.append(ref)
    return refs


def best_group_advantage(
    price_tier_refs, kind: str, *, channel_ref: str = "", now=None
) -> GroupAdvantage | None:
    """A melhor vantagem do TIPO entre os grupos do cliente: UMA só, sem acumular.

    ``discount`` = a ``Promotion`` ``grupo-<ref>`` de maior percentual (o valor fixo só
    quando não há percentual); ``price_list`` = a lista de preço do grupo de maior
    prioridade que tem uma; os demais tipos = a ``PriceTierAdvantage`` ativa de maior
    prioridade. Cliente em Equipe (−30%) e Aliança (−15%) fica com UMA: os −30%.
    """
    refs = _tier_refs(price_tier_refs)
    if not refs:
        return None
    if kind == "discount":
        return _best_group_discount(refs, channel_ref=channel_ref, now=now)
    if kind == "price_list":
        return _best_group_listing(refs)
    if kind == "free_shipping":
        return _best_group_free_shipping(refs)
    return _best_typed_advantage(refs, kind)


def customer_price_tier_refs(customer_ref: str) -> list[str]:
    """Os grupos do cliente, por ref: UMA consulta, sem carregar o cliente."""
    ref = str(customer_ref or "").strip()
    if not ref:
        return []
    from shopman.guestman.models import PriceTier

    return list(
        PriceTier.objects.filter(customers__ref=ref).order_by("-priority", "name").values_list("ref", flat=True)
    )


def free_shipping_min_order_q(advantage: Any) -> int:
    """O pedido mínimo do frete grátis do grupo, em centavos. ``0`` = sempre."""
    config = getattr(advantage, "config", None) or {}
    try:
        return max(0, int(config.get("min_order_q") or 0))
    except (TypeError, ValueError):
        return 0


def _best_group_free_shipping(refs: list[str]) -> GroupAdvantage | None:
    """O frete grátis que MAIS favorece o cliente: o de menor pedido mínimo.

    Dois grupos com frete grátis não somam nada (a taxa só zera uma vez); o que
    importa ao cliente é a partir de quanto ele já ganha. Empate no mínimo: a
    prioridade da vantagem e depois a do grupo dizem qual grupo dá o nome.
    """
    from shopman.guestman.models import PriceTierAdvantage

    advantages = list(
        PriceTierAdvantage.objects.filter(
            tier__ref__in=refs, kind=PriceTierAdvantage.Kind.FREE_SHIPPING, is_active=True
        )
        .select_related("tier")
        .order_by("-priority", "-tier__priority", "id")
    )
    if not advantages:
        return None
    advantage = min(advantages, key=free_shipping_min_order_q)  # min é estável: a ordem desempata
    return GroupAdvantage(
        kind="free_shipping",
        tier_ref=advantage.tier.ref,
        label=advantage.tier.name or "",
        value=advantage,
    )


def _best_group_discount(refs: list[str], *, channel_ref: str, now) -> GroupAdvantage | None:
    from django.utils import timezone

    from shopman.shop.models import Promotion

    refset = set(refs)
    candidates = [
        promo
        for promo in get_active_promotions(now or timezone.now(), channel_ref=channel_ref)
        if not promo.birthday_only
        and promo.type in (Promotion.PERCENT, Promotion.FIXED)
        and int(promo.value or 0) > 0
        and refset.intersection(promo.customer_segments or [])
    ]
    if not candidates:
        return None
    promo = max(candidates, key=lambda p: (p.type == Promotion.PERCENT, int(p.value or 0)))
    tier_ref = next((r for r in refs if r in (promo.customer_segments or [])), "")
    return GroupAdvantage(kind="discount", tier_ref=tier_ref, label=promo.name or "", value=promo)


def _best_group_listing(refs: list[str]) -> GroupAdvantage | None:
    from shopman.guestman.models import PriceTier

    tier = (
        PriceTier.objects.filter(ref__in=refs)
        .exclude(listing_ref="")
        .order_by("-priority", "name")
        .first()
    )
    if tier is None:
        return None
    return GroupAdvantage(
        kind="price_list", tier_ref=tier.ref, label=tier.name or "", value=tier.listing_ref
    )


def _best_typed_advantage(refs: list[str], kind: str) -> GroupAdvantage | None:
    from shopman.guestman.models import PriceTierAdvantage

    advantage = (
        PriceTierAdvantage.objects.filter(tier__ref__in=refs, kind=kind, is_active=True)
        .select_related("tier")
        .order_by("-priority", "-tier__priority", "id")
        .first()
    )
    if advantage is None:
        return None
    return GroupAdvantage(
        kind=kind,
        tier_ref=advantage.tier.ref,
        label=advantage.tier.name or "",
        value=advantage,
    )


def customer_group_promotion(price_tier_refs, *, channel_ref: str, now=None) -> Any | None:
    """A melhor promoção de grupo entre os grupos do cliente, ou ``None``.

    É a mesma promoção que o ``DiscountModifier`` aplica sozinho no reprice (casa
    ``customer_segments`` com QUALQUER grupo do cliente): aqui ela só é NOMEADA, para o
    balcão saber que o desconto vai entrar. Aniversariante fica de fora (tem aviso
    próprio), e promoção de SKU/coleção também vale: o rótulo diz o grupo, a linha
    diz em quais itens o desconto entrou.

    Com mais de uma, ganha a de maior percentual; o valor fixo só quando não há
    percentual. É o rótulo do balcão, não a conta: a conta é do motor, item a item.
    """
    best = best_group_advantage(price_tier_refs, "discount", channel_ref=channel_ref, now=now)
    return best.value if best is not None else None


def group_discount_label(promo: Any) -> str:
    """"Aliança Francesa · 10%" ou "Aliança Francesa · R$ 2,00"."""
    from shopman.utils.monetary import format_money

    from shopman.shop.models import Promotion

    if promo is None:
        return ""
    value = int(promo.value or 0)
    amount = f"{min(value, 100)}%" if promo.type == Promotion.PERCENT else f"R$ {format_money(value)}"
    return f"{promo.name} · {amount}"


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


#: Prefixo do cupom que a Concierge emite: o código diz, no Admin e no pedido, de onde veio.
CONCIERGE_COUPON_PREFIX = "CONCIERGE-"


def is_concierge_coupon(code: str | None) -> bool:
    return str(code or "").upper().startswith(CONCIERGE_COUPON_PREFIX)


def issue_concierge_coupon(
    *,
    value_q: int,
    min_order_q: int,
    channel_ref: str,
    conversation_id: int,
    valid_for,
) -> str:
    """Emite o cupom de uso único do desconto da Concierge e devolve o código.

    É um cupom como o do site (``Promotion`` de valor fixo + ``Coupon`` com
    ``max_uses=1``), para que o desconto passe pelas MESMAS portas: escopo de
    canal, pedido mínimo, "maior desconto ganha" e uso contado no commit. O
    ``min_order_q`` é o subtotal mínimo em que o valor ainda cabe no teto: se o
    cliente esvaziar a sacola depois, o cupom para de valer sozinho.

    O canal é obrigatório: promoção sem canal vale em todos, e o desconto da
    Concierge vale só no canal dela.
    """
    import secrets

    from django.utils import timezone

    from shopman.shop.models import Channel, Coupon, Promotion

    if value_q <= 0:
        raise ValueError("value_q deve ser > 0")
    channel = Channel.objects.filter(ref=channel_ref).first()
    if channel is None:
        raise ValueError(f"canal inexistente: {channel_ref!r}")
    token = secrets.token_hex(4).upper()
    now = timezone.now()
    promotion = Promotion.objects.create(
        ref=f"concierge-{token.lower()}",
        name=f"Desconto da Concierge (conversa {conversation_id})",
        type=Promotion.FIXED,
        value=int(value_q),
        valid_from=now,
        valid_until=now + valid_for,
        min_order_q=max(0, int(min_order_q)),
        is_active=True,
    )
    promotion.channels.set([channel])
    code = f"{CONCIERGE_COUPON_PREFIX}{token}"
    Coupon.objects.create(code=code, promotion=promotion, max_uses=1)
    return code


def withdraw_coupon(code: str) -> None:
    """Desliga um cupom emitido que não chegou a valer (nada aplicado)."""
    from shopman.shop.models import Coupon

    Coupon.objects.filter(code=code).update(is_active=False)


def match_delivery_zone(postal_code: str, neighborhood: str) -> Any | None:
    """A DeliveryZone ativa de maior prioridade, ou ``None``."""
    from shopman.shop.models import DeliveryZone

    return DeliveryZone.match(postal_code=postal_code, neighborhood=neighborhood)


def match_distance_band(distance_km: float) -> Any | None:
    """A faixa de distância ativa que cobre ``distance_km``, ou ``None``."""
    from shopman.shop.models import DeliveryDistanceBand

    return DeliveryDistanceBand.match(distance_km)
