"""Shared BOM expansion for Recipe-derived materialization.

A Recipe's technical sheet can reference sub-products that have their own
active Recipe (multilevel BOM). Both the nutrition derivation
(:mod:`shopman.shop.services.nutrition_from_recipe`) and the dietary
derivation (:mod:`shopman.shop.services.dietary_from_recipe`) need the same
thing: the flat list of *leaf* insumos behind a finished product.

``expand_recipe_items`` walks the tree, recursing into sub-recipes with
cycle protection (``MAX_BOM_DEPTH``) and skipping optional alternatives.
``item.quantity`` is scaled by the accumulated coefficient so callers that
do per-unit math (nutrition) get correct quantities; callers that only need
ingredient identity (dietary) ignore it.
"""

from __future__ import annotations

import logging
from decimal import Decimal

logger = logging.getLogger(__name__)

MAX_BOM_DEPTH = 5


def expand_recipe_items(
    recipe, *, coefficient: Decimal = Decimal("1"), depth: int = 0
) -> list:
    """Return the leaf RecipeItems behind ``recipe`` (sub-recipes expanded)."""
    if depth > MAX_BOM_DEPTH:
        logger.warning("recipe_bom: recursive recipe depth exceeded for %s", recipe.ref)
        return []

    try:
        from shopman.craftsman.services.recipes import get_active_recipe_for_output_sku
    except ImportError:
        return []

    expanded: list = []
    for item in recipe.items.filter(is_optional=False).order_by("-quantity", "sort_order"):
        sub_recipe = get_active_recipe_for_output_sku(item.input_sku)
        if sub_recipe:
            sub_coefficient = coefficient * (item.quantity / sub_recipe.batch_size)
            expanded.extend(
                expand_recipe_items(sub_recipe, coefficient=sub_coefficient, depth=depth + 1)
            )
            continue
        item.quantity = item.quantity * coefficient
        expanded.append(item)
    return expanded


def item_quantity_grams(item) -> Decimal | None:
    """Massa em gramas do item da ficha, ou ``None`` quando falta a ponte.

    Peso converte pela física (``shopman.utils.units``). Volume e contagem
    **não têm** caminho definicional até grama — a ponte é o perfil do insumo
    (``density_g_per_ml`` / ``unit_weight_g`` em ``RecipeItem.meta``). Sem o
    perfil, o item não tem massa conhecida, e cada consumidor decide o que
    fazer com isso: a nutrição o deixa de fora da soma (rótulo incompleto é
    melhor que rótulo inventado), o peso da peça recusa derivar (soma
    incompleta viraria um peso anunciado sem relação com a peça).

    Mora aqui, e não na nutrição, porque virou a régua de três derivações.
    """
    from shopman.utils import units

    unit = str(getattr(item, "unit", "") or "").strip()
    quantity = Decimal(str(item.quantity))
    meta = item.meta if isinstance(item.meta, dict) else {}
    item_dimension = units.dimension(unit)

    if item_dimension == units.MASS:
        return units.convert(quantity, unit, "g")

    if item_dimension == units.VOLUME:
        density = positive_decimal(meta.get("density_g_per_ml"))
        if density is None:
            return None
        return units.convert(quantity, unit, "ml") * density

    if item_dimension == units.COUNT:
        unit_weight = positive_decimal(meta.get("unit_weight_g"))
        if unit_weight is None:
            return None
        return units.convert(quantity, unit, "un") * unit_weight

    return None


def positive_decimal(value) -> Decimal | None:
    """``Decimal`` estritamente positivo, ou ``None`` — ponte inválida é ponte ausente."""
    from decimal import InvalidOperation

    try:
        decimal = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return decimal if decimal > 0 else None
