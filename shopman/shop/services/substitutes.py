"""Centralized substitutes service.

Single point of access for finding available substitute products across all
contexts (stock-error modal, API). Substitutes are shown ONLY when the
chosen SKU is unavailable — they replace, never recommend.
"""
from __future__ import annotations

import logging
from decimal import Decimal

from django.conf import settings
from shopman.utils.monetary import format_money

from shopman.shop.adapters import get_adapter

HAS_STOCKMAN = True
STOREFRONT_CHANNEL_REF: str = getattr(settings, "SHOPMAN_STOREFRONT_CHANNEL_REF", "web")

logger = logging.getLogger(__name__)


def find(sku: str, *, qty: Decimal = Decimal("1"), channel: str | None = None, limit: int = 4) -> list[dict]:
    """
    Busca substitutos disponíveis para o canal.
    Ponto único de consumo para todos os contextos.

    Returns:
        [{"sku", "name", "price_q", "price_display", "available_qty", "can_order", "target_qty"}, ...]

    ``target_qty`` is ``min(requested_qty, sub.available_qty)`` — the amount
    the client should add when the shopper accepts this substitute in a
    1-click swap. Minimum of 1 so the button always does something useful.
    """
    catalog = get_adapter("catalog")
    if not catalog:
        return []

    try:
        candidates = catalog.find_substitutes(sku, limit=limit * 3)
        if not candidates:
            return []
    except Exception as e:
        logger.warning("substitutes_candidates_failed sku=%s: %s", sku, e, exc_info=True)
        return []

    # A fronteira do tenant, sobre a similaridade do Core: o Offerman sabe o que
    # se PARECE com o quê; a casa decide o que pode ser oferecido no lugar.
    candidates = _same_boundary(sku, candidates)
    if not candidates:
        return []

    channel_ref = channel or STOREFRONT_CHANNEL_REF

    # Build availability map for all candidates in one batch query
    avail_map: dict[str, dict | None] = {}
    if HAS_STOCKMAN:
        try:
            from shopman.stockman.services.availability import availability_for_skus

            from shopman.shop.adapters import stock as stock_adapter

            skus = [p.sku for p in candidates]
            scope = stock_adapter.get_channel_scope(channel_ref)
            avail_map = availability_for_skus(
                skus,
                safety_margin=scope["safety_margin"],
                allowed_positions=scope["allowed_positions"],
                excluded_positions=scope.get("excluded_positions"),
            expiry_margin_days=scope.get("expiry_margin_days", 0),
            include_nonconforming=scope.get("sells_nonconforming", True),
            )
        except Exception as e:
            logger.warning("substitutes_availability_failed: %s", e, exc_info=True)

    # Build price map via listing
    price_map: dict[str, int] = {}
    try:
        from shopman.shop.models import Channel

        channel_obj = Channel.objects.filter(ref=channel_ref).first()
        listing_ref = channel_obj.ref if channel_obj else None
        if listing_ref:
            skus = [p.sku for p in candidates]
            price_map = catalog.bulk_listing_price_map(skus, listing_ref)
    except Exception as e:
        logger.warning("substitutes_price_map_failed: %s", e, exc_info=True)

    result = []
    for product in candidates:
        if len(result) >= limit:
            break

        raw_avail = avail_map.get(product.sku)
        can_order, available_qty = _resolve_availability(raw_avail, product, qty)

        # Skip if not orderable and stockman is active
        if HAS_STOCKMAN and raw_avail is not None and not can_order:
            continue

        price_q = price_map.get(product.sku) or product.base_price_q
        price_display = f"R$ {format_money(price_q)}" if price_q else None

        target_qty = _target_qty(qty, available_qty)

        result.append({
            "sku": product.sku,
            "name": product.name,
            "image_url": getattr(product, "image_url", "") or "",
            "price_q": price_q,
            "price_display": price_display,
            "available_qty": int(available_qty),
            "can_order": can_order,
            "target_qty": target_qty,
        })

    return result


def _same_boundary(sku: str, candidates: list) -> list:
    """Corta quem cruza a fronteira que a casa declarou em ``suggestion.substitute``.

    O caso canônico é o **sabor**: doce substitui doce, salgado substitui
    salgado. Isso é política do tenant e não cabe no Core — o Offerman não sabe
    o que é doce, e não deveria.

    ⚠️ **Ausência de dado não é divergência.** Só corta quando os DOIS lados têm
    valor e eles diferem. Excluir quem está sem `sabor` cadastrado recriaria,
    uma camada acima, exatamente o defeito que o refino do Core acabou de
    remover: exigir um dado curado para o produto ter substituto.

    Regra desligada ou sem ``must_match`` não corta nada.
    """
    from shopman.shop.rules.engine import get_rule_params

    params = get_rule_params("suggestion.substitute") or {}
    must_match = params.get("must_match") or []
    if not must_match:
        return candidates

    from shopman.offerman.models import Product

    from shopman.shop.services import attributes

    reference = Product.objects.filter(sku=sku).first()
    if reference is None:
        return candidates

    kept = candidates
    for ref_attr in must_match:
        try:
            wanted = attributes.get(reference, ref_attr)
        except Exception:
            # Atributo saiu do registro depois de a regra citá-lo: a regra
            # perdeu o sentido, e cortar por ela seria pior que não cortar.
            logger.warning(
                "substitutes: regra cita atributo '%s' que o registro não conhece.", ref_attr,
            )
            continue
        if wanted is None:
            continue
        by_sku = attributes.get_many(kept, ref_attr)
        kept = [
            c for c in kept
            if by_sku.get(c.sku) is None or by_sku[c.sku] == wanted
        ]
    return kept


def _target_qty(requested: Decimal, available: Decimal) -> int:
    """Amount to add on a 1-click swap: ``min(requested, available)`` ≥ 1."""
    req_i = int(requested) if requested else 1
    avail_i = int(available) if available else 0
    if avail_i <= 0:
        return max(1, req_i)
    return max(1, min(req_i, avail_i))


def _resolve_availability(raw_avail: dict | None, product, qty: Decimal) -> tuple[bool, Decimal]:
    """Return (can_order, available_qty) from raw availability result."""
    if not product.is_sellable:
        return False, Decimal("0")
    if raw_avail is None:
        # No stockman data — assume available
        return True, Decimal("0")
    is_paused = raw_avail.get("is_paused", False) or not product.is_sellable
    availability_policy = raw_avail.get("availability_policy", "planned_ok")
    total_promisable = raw_avail.get("total_promisable", Decimal("0"))
    if availability_policy == "demand_ok" and not is_paused:
        return True, qty
    can_order = total_promisable >= qty and not is_paused
    return can_order, total_promisable
