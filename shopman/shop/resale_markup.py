"""Markup da revenda — ``Shop.defaults["purchase"]`` + resolução por categoria.

Sugere o preço de venda de uma coisa comprada quando o operador liga
"Permitir revenda" no Compras. Decisão do dono (24/09/2026): markup
configurável por categoria, com um padrão da loja de **50%**.

**Semântica** (markup sobre o custo, não margem sobre o preço):
``preço = custo × (1 + markup/100)``. 50% ⇒ ×1,5 (margem de 33%);
150% ⇒ ×2,5 (margem de 60%).

**Onde mora** — no mesmo bloco tipado da política de Compras
(``Shop.defaults["purchase"]``, editado na página "Compras" do Admin):

- ``resale_markup_pct`` — padrão da loja (inteiro, %);
- ``resale_markup_by_collection`` — ``{ref da coleção: %}``; a categoria de um
  item é a coleção principal do produto (``CollectionItem.is_primary``) ou, se
  o item ainda não se vende, a coleção onde "Permitir revenda" o coloca
  (:data:`RESALE_COLLECTION_REF`).

**Arredondamento**: para cima, até o real inteiro. A tabela de preços da casa
fala real cheio (R$ 42, R$ 31, R$ 15 — nenhum dos 38 itens de revenda tem
centavos), e arredondar para baixo venderia abaixo do markup declarado.

A sugestão é só isso: vem pré-preenchida e editável. Quem decide o preço é o
operador; sem custo conhecido não há sugestão (nunca se inventa custo).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal

DEFAULT_RESALE_MARKUP_PCT = 50
#: Teto de sanidade: 1000% é ×11 — acima disso é dedo escorregado.
MAX_RESALE_MARKUP_PCT = 1000
#: Coleção onde "Permitir revenda" põe um item novo (``sku_records.start_selling``).
RESALE_COLLECTION_REF = "mercearia"


def _coerce_pct(value, *, fallback: int | None) -> int | None:
    if isinstance(value, bool):
        return fallback
    try:
        pct = int(value)
    except (TypeError, ValueError):
        return fallback
    if pct < 0 or pct > MAX_RESALE_MARKUP_PCT:
        return fallback
    return pct


@dataclass
class ResaleMarkup:
    """Markup resolvido (defaults ← ``Shop.defaults["purchase"]``)."""

    default_pct: int = DEFAULT_RESALE_MARKUP_PCT
    by_collection: dict[str, int] = field(default_factory=dict)

    @classmethod
    def from_defaults(cls, defaults: dict | None) -> ResaleMarkup:
        block = defaults.get("purchase") if isinstance(defaults, dict) else None
        block = block if isinstance(block, dict) else {}
        raw = block.get("resale_markup_by_collection")
        by_collection = {
            str(ref): pct
            for ref, value in (raw.items() if isinstance(raw, dict) else [])
            if (pct := _coerce_pct(value, fallback=None)) is not None
        }
        return cls(
            default_pct=_coerce_pct(block.get("resale_markup_pct"), fallback=DEFAULT_RESALE_MARKUP_PCT),
            by_collection=by_collection,
        )

    def pct_for(self, collection_ref: str | None) -> tuple[int, str]:
        """``(markup %, de onde veio)`` — ``collection_ref`` ou ``""`` (padrão da loja)."""
        if collection_ref and collection_ref in self.by_collection:
            return self.by_collection[collection_ref], collection_ref
        return self.default_pct, ""


def resolve_resale_markup() -> ResaleMarkup:
    from shopman.shop.models import Shop

    shop = Shop.load()
    return ResaleMarkup.from_defaults(getattr(shop, "defaults", None) if shop else None)


def suggested_price_q(cost_q: int, markup_pct: int) -> int:
    """Custo × (1 + markup), para cima até o real inteiro. Centavos inteiros."""
    if cost_q <= 0:
        return 0
    raw = Decimal(cost_q) * (Decimal(100) + Decimal(markup_pct)) / Decimal(100)
    reais = (raw / Decimal(100)).to_integral_value(rounding=ROUND_CEILING)
    return int(reais * 100)


def unit_costs_map(skus) -> dict[str, int]:
    """Custo por unidade-base de cada SKU: fornecedor preferido, senão a última compra.

    SKU sem custo conhecido fica de fora — e aí não há sugestão: nunca se
    inventa custo. Duas consultas para a lista inteira.
    """
    from shopman.buyman.models import SupplierMaterialCost
    from shopman.stockman.models import Move

    skus = [sku for sku in dict.fromkeys(skus) if sku]
    costs: dict[str, int] = {}
    rows = (
        SupplierMaterialCost.objects.filter(material__sku__in=skus, cost_q__gt=0)
        .select_related("material", "conversion")
        .order_by("-is_preferred", "-updated_at")
    )
    for row in rows:
        sku = row.material.sku
        if sku in costs:
            continue
        factor = Decimal(row.conversion.to_base_factor) if row.conversion_id else Decimal(1)
        if factor > 0:
            costs[sku] = int((Decimal(row.cost_q) / factor).quantize(Decimal(1), rounding=ROUND_HALF_UP))

    missing = [sku for sku in skus if sku not in costs]
    if missing:
        moves = (
            Move.objects.filter(quant__sku__in=missing, kind=Move.Kind.BUY, delta__gt=0)
            .select_related("quant")
            .order_by("-timestamp", "-pk")
        )
        for move in moves:
            sku = move.quant.sku
            if sku in costs:
                continue
            metadata = move.metadata or {}
            try:
                total = Decimal(str(metadata.get("purchase_total_cost_q") or 0))
                base_qty = Decimal(str(metadata.get("purchase_base_qty") or move.delta))
            except ArithmeticError:
                continue
            if total > 0 and base_qty > 0:
                costs[sku] = int((total / base_qty).quantize(Decimal(1), rounding=ROUND_HALF_UP))
    return costs


def primary_collections_map(skus) -> dict[str, tuple[str, str]]:
    """``{sku: (ref, nome)}`` da coleção principal do produto de mesmo SKU."""
    from shopman.offerman.models import CollectionItem

    return {
        sku: (ref, name)
        for sku, ref, name in CollectionItem.objects.filter(product__sku__in=list(skus), is_primary=True)
        .values_list("product__sku", "collection__ref", "collection__name")
    }
