"""Reposição de Compras — ``Shop.defaults["purchase"]`` dataclass + resolução.

Política do cálculo de reposição do app Compras, editável no Admin (página
"Compras" do ShopAdmin) e lida pela projection do operador
(``shopman/backstage/projections/purchase.py``):

- ``consumption_window_days`` — janela do consumo médio diário lido do ledger
  do Stockman.
- ``review_period_days`` — cadência de revisão de compras (dias entre pedidos).
- ``safety_days`` — margem de segurança em dias de consumo.
- ``min_lead_time_days`` — piso do prazo de entrega sem histórico nem cadastro.
- ``lead_time_history_days`` — janela do histórico pedido→entrega da mediana.
- ``lead_time_max_days`` — amostras acima disso são descartadas como ruído.

Aqui mora o source-of-truth tipado (dataclass), seguindo o padrão
dataclass-driven do ``Shop.defaults`` (espelha ``loyalty_config``).
"""

from __future__ import annotations

from dataclasses import dataclass, fields

DEFAULT_CONSUMPTION_WINDOW_DAYS = 14
DEFAULT_REVIEW_PERIOD_DAYS = 3
DEFAULT_SAFETY_DAYS = 2
DEFAULT_MIN_LEAD_TIME_DAYS = 1
DEFAULT_LEAD_TIME_HISTORY_DAYS = 120
DEFAULT_LEAD_TIME_MAX_DAYS = 45

# Piso por chave: janelas de leitura não podem ser 0 (não haveria o que medir);
# margens podem ser desligadas com 0.
POLICY_MINIMUMS: dict[str, int] = {
    "consumption_window_days": 1,
    "review_period_days": 0,
    "safety_days": 0,
    "min_lead_time_days": 0,
    "lead_time_history_days": 1,
    "lead_time_max_days": 1,
}


@dataclass
class PurchasePolicy:
    """Política de reposição resolvida (defaults ← Shop.defaults["purchase"])."""

    consumption_window_days: int = DEFAULT_CONSUMPTION_WINDOW_DAYS
    review_period_days: int = DEFAULT_REVIEW_PERIOD_DAYS
    safety_days: int = DEFAULT_SAFETY_DAYS
    min_lead_time_days: int = DEFAULT_MIN_LEAD_TIME_DAYS
    lead_time_history_days: int = DEFAULT_LEAD_TIME_HISTORY_DAYS
    lead_time_max_days: int = DEFAULT_LEAD_TIME_MAX_DAYS

    @classmethod
    def from_defaults(cls, defaults: dict | None) -> PurchasePolicy:
        """Constrói a partir de ``Shop.defaults`` (chaves ausentes → defaults)."""
        block: dict = {}
        if isinstance(defaults, dict) and isinstance(defaults.get("purchase"), dict):
            block = defaults["purchase"]
        return cls(**{
            spec.name: _coerce_day_count(
                block.get(spec.name),
                fallback=spec.default,
                minimum=POLICY_MINIMUMS[spec.name],
            )
            for spec in fields(cls)
        })

    def to_dict(self) -> dict[str, int]:
        return {spec.name: getattr(self, spec.name) for spec in fields(self)}


def _coerce_day_count(value, *, fallback: int, minimum: int) -> int:
    try:
        coerced = int(value)
    except (TypeError, ValueError):
        return fallback
    return max(minimum, coerced)


def resolve_purchase_policy() -> PurchasePolicy:
    """Política de reposição efetiva, a partir do ``Shop`` singleton."""
    from shopman.shop.models import Shop

    shop = Shop.load()
    defaults = getattr(shop, "defaults", None) if shop else None
    return PurchasePolicy.from_defaults(defaults)
