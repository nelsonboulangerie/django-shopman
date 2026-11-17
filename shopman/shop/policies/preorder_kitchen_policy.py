"""Quando a encomenda chega à Cozinha — ``Shop.defaults["preorder_kitchen"]``.

Decisão do dono (09/11/2026): no dia da encomenda, o card chega à Cozinha em
``hora combinada − tempo de preparo − antecedência``. Exemplo: retirada às 17h,
30 min de preparo e 15 min de antecedência → o card chega às 16h15. Chegar à
Cozinha não é "Em preparo": o pedido espera o "Iniciar" do posto.

Chaves (todas opcionais; sem o bloco, valem os padrões declarados abaixo):

- ``lead_minutes`` — antecedência, em minutos, somada ao preparo. Padrão 15.
- ``default_prep_minutes`` — o preparo do SKU que não tem tempo próprio. É o
  fallback declarado: SKU sem configuração conta com ele. Padrão 30.
- ``prep_minutes_by_sku`` — ``{sku: minutos}``, o preparo pré-configurado por
  SKU. Um pedido com várias linhas usa o MAIOR preparo entre elas (as estações
  trabalham em paralelo; a última a terminar dita a chegada).

Encomenda SEM hora combinada ("a combinar") chega na abertura da loja no dia;
sem expediente declarado para o dia, às 00:05 (a régua anterior).

Configuração de loja: mora na ``Shop`` (ADR-042), nunca em env ou settings.
Mesmo padrão dataclass-driven de ``purchase_policy``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

DEFAULT_LEAD_MINUTES = 15
DEFAULT_PREP_MINUTES = 30

BLOCK = "preorder_kitchen"


@dataclass
class PreorderKitchenPolicy:
    lead_minutes: int = DEFAULT_LEAD_MINUTES
    default_prep_minutes: int = DEFAULT_PREP_MINUTES
    prep_minutes_by_sku: dict[str, int] = field(default_factory=dict)

    @classmethod
    def from_defaults(cls, defaults: dict | None) -> PreorderKitchenPolicy:
        block: dict = {}
        if isinstance(defaults, dict) and isinstance(defaults.get(BLOCK), dict):
            block = defaults[BLOCK]
        by_sku_raw = block.get("prep_minutes_by_sku")
        by_sku: dict[str, int] = {}
        if isinstance(by_sku_raw, dict):
            for sku, minutes in by_sku_raw.items():
                value = _minutes(minutes, fallback=None)
                if sku and value is not None:
                    by_sku[str(sku)] = value
        return cls(
            lead_minutes=_minutes(block.get("lead_minutes"), fallback=DEFAULT_LEAD_MINUTES),
            default_prep_minutes=_minutes(block.get("default_prep_minutes"), fallback=DEFAULT_PREP_MINUTES),
            prep_minutes_by_sku=by_sku,
        )

    def prep_minutes_for(self, skus) -> int:
        """O preparo do pedido: o maior entre as linhas; SKU sem tempo próprio usa o padrão."""
        values = [self.prep_minutes_by_sku.get(str(sku), self.default_prep_minutes) for sku in skus if sku]
        return max(values) if values else self.default_prep_minutes


def _minutes(value, *, fallback):
    if isinstance(value, bool):
        return fallback
    try:
        coerced = int(value)
    except (TypeError, ValueError):
        return fallback
    return coerced if coerced >= 0 else fallback


def resolve_preorder_kitchen_policy() -> PreorderKitchenPolicy:
    """Política efetiva, a partir do ``Shop`` singleton."""
    from shopman.shop.models import Shop

    shop = Shop.load()
    defaults = getattr(shop, "defaults", None) if shop else None
    return PreorderKitchenPolicy.from_defaults(defaults)
