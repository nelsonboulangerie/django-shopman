"""Custo de um produto: o VIVO (para precificar) e o CONGELADO (para contar história).

ADR-023 (aceita, dono, 19/08; ligada de ponta a ponta em 11/11, F3): **dois
custos**. Mora no orquestrador porque precisa da receita (Craftsman) e do custo do
insumo (Buyman) ao mesmo tempo, e cores não se importam (ADR-001).

**Custo vivo** (:class:`RecipeCostBackend`, ligado em ``OFFERMAN["COST_BACKEND"]``):
responde "quanto custa isto hoje" para a margem do Admin e o "R$ de custo" da
sobra no B.I. Por unidade do produto:

- **Produzido aqui** (tem ficha ativa)::

      Σ (quantidade LÍQUIDA ÷ aproveitamento, na unidade-base do insumo)
        × custo por unidade-base do fornecedor preferencial
      ÷ rendimento da ficha

  Sub-receita (o levain, a massa-mãe) entra pelo custo dela, pela mesma conta,
  até 5 níveis (a mesma régua de ciclo do Craftsman).
- **Revenda** (sem ficha, mesmo SKU no cadastro de compra): o custo preferencial
  do próprio ``Material``, convertido para a unidade em que o produto se vende.
  O porteiro do SKU (``shop/services/sku_namespace.py``) garante que as duas
  pontas falem a mesma unidade; a conversão está aqui para não depender disso.

**Custo congelado** (:func:`work_order_cost_snapshot`): o que cada insumo
CONSUMIDO custava no instante do ``finish`` da fornada, gravado uma vez em
``WorkOrder.meta["cost_snapshot"]`` pelo receiver
``shop/handlers/production_cost.py``. Nunca recalculado: a margem de agosto não
muda quando a farinha sobe em setembro.

**Sem custo, sem chute** (ADR-023 §4): basta um insumo obrigatório sem custo
preferencial, ou uma unidade que não converte, para o custo vivo ser ``None`` e o
congelado registrar a lacuna. Zero é um número; ausência não é. E a ausência
**grita**: :meth:`RecipeCostBackend.get_cost_gap` diz ao operador o que falta, em
português, na coluna de custo do catálogo.
"""

from __future__ import annotations

import logging
from decimal import ROUND_HALF_UP, Decimal

from django.utils import timezone

logger = logging.getLogger(__name__)

MAX_DEPTH = 5
SNAPSHOT_KEY = "cost_snapshot"


class _NoCost(Exception):
    """Algum pedaço da conta não tem custo conhecido: a resposta inteira é None.

    ``args[0]`` é o motivo, escrito para o operador ler.
    """

    @property
    def reason(self) -> str:
        return str(self.args[0]) if self.args else "Custo desconhecido."


def _qty(value: Decimal) -> str:
    """Quantidade como texto sem zeros de enfeite ("10", "0.5")."""
    return format(value.normalize(), "f")


def _round_q(value: Decimal) -> int:
    return int(value.quantize(Decimal(1), rounding=ROUND_HALF_UP))


class RecipeCostBackend:
    """``CostBackend`` do Offerman: centavos por unidade do produto, ou None."""

    def get_cost(self, sku: str) -> int | None:
        try:
            per_unit = _cost_per_product_unit(sku)
        except _NoCost:
            return None
        except Exception:
            logger.warning("cost.recipe_cost_failed sku=%s", sku, exc_info=True)
            return None
        return _round_q(per_unit)

    def get_cost_gap(self, sku: str) -> str | None:
        """Por que ``get_cost`` responde ``None``; ``None`` quando há custo."""
        try:
            _cost_per_product_unit(sku)
        except _NoCost as exc:
            return exc.reason
        except Exception:
            logger.warning("cost.recipe_cost_failed sku=%s", sku, exc_info=True)
            return f"O cálculo do custo de {sku} falhou. O erro está no log."
        return None


def _cost_per_product_unit(sku: str) -> Decimal:
    """Centavos (Decimal) por unidade do produto: ficha primeiro, revenda depois."""
    from shopman.craftsman.services.recipes import get_active_recipe_for_output_sku

    if get_active_recipe_for_output_sku(sku) is not None:
        return _cost_per_output_unit(sku, depth=0)
    material = _material(sku)
    if material is None:
        raise _NoCost(f"{sku} não tem ficha técnica ativa nem cadastro de compra.")
    return _material_cost(material, Decimal(1), _product_unit(sku) or material.unit)


def _product_unit(sku: str) -> str:
    from shopman.offerman.models import Product

    return Product.objects.filter(sku=sku).values_list("unit", flat=True).first() or ""


def _material(sku: str):
    from shopman.buyman.models import Material

    return Material.objects.filter(sku=sku).first()


def _material_cost(material, quantity: Decimal, unit: str) -> Decimal:
    """Custo de ``quantity`` ``unit`` de um insumo comprado, pelo fornecedor preferencial."""
    return _material_unit_cost(material, unit) * quantity


def _material_unit_cost(material, unit: str) -> Decimal:
    """Centavos (Decimal) de UMA ``unit`` do insumo, pelo custo preferencial atual."""
    from shopman.buyman.models import SupplierMaterialCost
    from shopman.utils import units

    cost = (
        SupplierMaterialCost.objects.filter(material=material, is_preferred=True)
        .select_related("conversion", "material")
        .first()
    )
    if cost is None:
        raise _NoCost(f"{material.sku} não tem custo preferencial no Compras.")
    if not unit:
        raise _NoCost(f"{material.sku} foi lançado sem unidade; o custo não tem como ser convertido.")
    try:
        in_base = units.convert(Decimal(1), unit, material.unit)
    except Exception as exc:
        raise _NoCost(
            f"{material.sku}: a unidade '{unit}' não converte para '{material.unit}', a do cadastro de compra."
        ) from exc
    return in_base * cost.cost_per_base_unit


def _cost_per_output_unit(sku: str, *, depth: int) -> Decimal:
    """Centavos (Decimal, sem arredondar) por unidade declarada da saída da ficha."""
    from shopman.craftsman.services.recipes import get_active_recipe_for_output_sku

    if depth > MAX_DEPTH:
        raise _NoCost(f"A ficha de {sku} passa de {MAX_DEPTH} níveis de sub-receita.")
    recipe = get_active_recipe_for_output_sku(sku)
    if recipe is None:
        raise _NoCost(f"{sku} não tem ficha técnica ativa nem cadastro de compra.")
    if not recipe.batch_size:
        raise _NoCost(f"A ficha de {sku} não tem rendimento.")
    total = Decimal(0)
    items = list(recipe.items.filter(is_optional=False))
    if not items:
        raise _NoCost(f"A ficha de {sku} não tem insumo obrigatório.")
    for item in items:
        gross = Decimal(item.quantity) / (Decimal(item.usable_factor) or Decimal(1))
        total += _input_cost(item.input_sku, gross, item.unit, depth=depth)
    return total / Decimal(recipe.batch_size)


def _input_cost(input_sku: str, quantity: Decimal, unit: str, *, depth: int) -> Decimal:
    """Custo de ``quantity`` ``unit`` de um insumo: comprado (Buyman) ou feito aqui."""
    material = _material(input_sku)
    if material is not None:
        return _material_cost(material, quantity, unit)
    # Feito aqui: a quantidade está na unidade em que a sub-ficha rende (a mesma
    # suposição do ``_expand_bom`` do Craftsman, que escala por ``batch_size``).
    return quantity * _cost_per_output_unit(input_sku, depth=depth + 1)


# ── Custo congelado ─────────────────────────────────────────────────────────


def work_order_cost_snapshot(work_order) -> dict:
    """O custo da fornada no instante em que é chamado (o ``finish``).

    Lê as linhas CONSUMPTION do ledger da ordem (a quantidade BRUTA que saiu do
    estoque) e prende a cada uma o custo unitário de agora. Linha sem custo vira
    lacuna com motivo, e a fornada inteira fica sem total: um total que esconde
    uma lacuna é zero disfarçado.
    """
    from shopman.craftsman.models import WorkOrderItem

    lines: list[dict] = []
    gaps: list[str] = []
    total = Decimal(0)
    consumption = work_order.items.filter(kind=WorkOrderItem.Kind.CONSUMPTION).order_by("pk")
    for item in consumption:
        quantity = Decimal(item.quantity)
        line = {"sku": item.item_ref, "quantity": _qty(quantity), "unit": item.unit or ""}
        try:
            unit_cost = _line_unit_cost(item.item_ref, item.unit or "")
        except _NoCost as exc:
            line["gap"] = exc.reason
            gaps.append(exc.reason)
        else:
            line_total = unit_cost * quantity
            total += line_total
            line["unit_cost"] = str(unit_cost.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP))
            line["cost_q"] = _round_q(line_total)
        lines.append(line)
    if not lines:
        gaps.append(f"A fornada {work_order.ref} fechou sem consumo de insumo no ledger.")

    output_quantity = sum(
        (Decimal(q) for q in work_order.items.filter(kind=WorkOrderItem.Kind.OUTPUT).values_list("quantity", flat=True)),
        Decimal(0),
    )
    complete = not gaps
    total_q = _round_q(total) if complete else None
    unit_cost_q = _round_q(total / output_quantity) if complete and output_quantity > 0 else None
    return {
        "frozen_at": timezone.now().isoformat(),
        "total_q": total_q,
        "unit_cost_q": unit_cost_q,
        "output_quantity": _qty(output_quantity),
        "lines": lines,
        "gaps": gaps,
    }


def _line_unit_cost(sku: str, unit: str) -> Decimal:
    """Centavos (Decimal) de UMA ``unit`` do que foi consumido: comprado ou feito aqui."""
    material = _material(sku)
    if material is not None:
        return _material_unit_cost(material, unit)
    # Sub-receita consumida (levain): o custo dela agora, na unidade em que rende.
    return _cost_per_output_unit(sku, depth=1)
