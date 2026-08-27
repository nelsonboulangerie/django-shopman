"""PurchaseCountProjection — read model da Contagem de insumos (aba Base do Compras).

A posição por insumo aqui é a soma CRUA do ledger (Σ quants físicos), não o
``available`` do board: a contagem física enxerga lote vencido na prateleira e
não desconta hold, e o ajuste do Stockman calcula o delta contra essa mesma
quantidade — se a tela mostrasse ``available``, a diferença exibida não bateria
com o Move lançado.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal

from django.apps import apps
from django.db.models import Sum

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CountItemProjection:
    sku: str
    name: str
    unit: str
    category: str
    isActive: bool
    systemQty: float


@dataclass(frozen=True)
class PurchaseCountProjection:
    items: tuple[CountItemProjection, ...]


def build_purchase_count() -> PurchaseCountProjection:
    Material = apps.get_model("buyman", "Material")
    materials = list(Material.objects.all().order_by("name"))
    system = system_qty_map([material.sku for material in materials])
    items = sorted(
        (
            CountItemProjection(
                sku=material.sku,
                name=material.name,
                unit=material.unit,
                category=_category(material),
                isActive=bool(material.is_active),
                systemQty=_number(system.get(material.sku, Decimal("0"))),
            )
            for material in materials
            # Inativo sem saldo não se conta; inativo COM saldo ainda ocupa prateleira.
            if material.is_active or system.get(material.sku)
        ),
        key=lambda item: (item.category, item.name),
    )
    return PurchaseCountProjection(items=tuple(items))


def system_qty_map(skus: list[str]) -> dict[str, Decimal]:
    """Σ(quants físicos) por SKU — quants futuros (planejamento) ficam de fora."""
    if not skus:
        return {}
    from shopman.stockman import stock

    rows = (
        stock.list_quants(include_future=False)
        .filter(sku__in=skus)
        .values("sku")
        .annotate(total=Sum("_quantity"))
    )
    return {row["sku"]: row["total"] or Decimal("0") for row in rows}


def _category(material) -> str:
    metadata = dict(getattr(material, "metadata", None) or {})
    nested = metadata.get("purchase")
    meta = {**metadata, **nested} if isinstance(nested, dict) else metadata
    value = meta.get("category")
    return str(value).strip() if value not in (None, "") else "Insumos"


def _number(value: Decimal) -> float:
    return float(value)
