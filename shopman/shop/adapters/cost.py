"""Custo vivo de um produto: a ficha técnica ativa × o custo preferencial dos insumos.

ADR-023 (aceita, dono, 19/08): **dois custos**. Este é o *vivo*, o que responde
"quanto custa fazer isto hoje" para a margem do Admin e o "R$ de custo" da sobra
no B.I. (V6-BI, prévia ``bi-sobra4``). Mora no orquestrador porque precisa da
receita (Craftsman) e do custo do insumo (Buyman) ao mesmo tempo, e cores não se
importam (ADR-001). Ligado em ``OFFERMAN["COST_BACKEND"]``.

A conta, por unidade do produto:

    Σ (quantidade LÍQUIDA ÷ aproveitamento, na unidade-base do insumo)
      × custo por unidade-base do fornecedor preferencial
    ÷ rendimento da ficha

Sub-receita (o levain, a massa-mãe) entra pelo custo dela, pela mesma conta, até
5 níveis (a mesma régua de ciclo do Craftsman).

**Sem custo, sem chute** (ADR-023 §4): basta um insumo obrigatório sem custo
preferencial, ou uma unidade que não converte, para a resposta ser ``None``. Zero
é um número; ausência não é. O custo *congelado* no fechamento do lote é outro
trabalho da mesma ADR e não mora aqui.
"""

from __future__ import annotations

import logging
from decimal import ROUND_HALF_UP, Decimal

logger = logging.getLogger(__name__)

MAX_DEPTH = 5


class _NoCost(Exception):
    """Algum pedaço da conta não tem custo conhecido: a resposta inteira é None."""


class RecipeCostBackend:
    """``CostBackend`` do Offerman: centavos por unidade do produto, ou None."""

    def get_cost(self, sku: str) -> int | None:
        try:
            per_unit = _cost_per_output_unit(sku, depth=0)
        except _NoCost:
            return None
        except Exception:
            logger.warning("cost.recipe_cost_failed sku=%s", sku, exc_info=True)
            return None
        return int(per_unit.quantize(Decimal(1), rounding=ROUND_HALF_UP))


def _cost_per_output_unit(sku: str, *, depth: int) -> Decimal:
    """Centavos (Decimal, sem arredondar) por unidade declarada da saída da ficha."""
    from shopman.craftsman.services.recipes import get_active_recipe_for_output_sku

    if depth > MAX_DEPTH:
        raise _NoCost
    recipe = get_active_recipe_for_output_sku(sku)
    if recipe is None or not recipe.batch_size:
        raise _NoCost
    total = Decimal(0)
    items = list(recipe.items.filter(is_optional=False))
    if not items:
        raise _NoCost
    for item in items:
        gross = Decimal(item.quantity) / (Decimal(item.usable_factor) or Decimal(1))
        total += _input_cost(item.input_sku, gross, item.unit, depth=depth)
    return total / Decimal(recipe.batch_size)


def _input_cost(input_sku: str, quantity: Decimal, unit: str, *, depth: int) -> Decimal:
    """Custo de ``quantity`` ``unit`` de um insumo: comprado (Buyman) ou feito aqui."""
    from shopman.buyman.models import Material, SupplierMaterialCost
    from shopman.utils import units

    material = Material.objects.filter(sku=input_sku).first()
    if material is not None:
        cost = (
            SupplierMaterialCost.objects.filter(material=material, is_preferred=True)
            .select_related("conversion")
            .first()
        )
        if cost is None:
            raise _NoCost
        try:
            in_base = units.convert(quantity, unit, material.unit)
        except Exception as exc:
            raise _NoCost from exc
        return in_base * cost.cost_per_base_unit
    # Feito aqui: a quantidade está na unidade em que a sub-ficha rende (a mesma
    # suposição do ``_expand_bom`` do Craftsman, que escala por ``batch_size``).
    return quantity * _cost_per_output_unit(input_sku, depth=depth + 1)
