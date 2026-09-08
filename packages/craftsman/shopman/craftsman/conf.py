"""
Craftsman Settings (vNext).

Supports two formats (dict takes priority):

    # Option 1: Dict
    CRAFTSMAN = {
        "DEMAND_BACKEND": "shopman.craftsman.contrib.demand.backend.OrderingDemandBackend",
    }

    # Option 2: Flat
    CRAFTSMAN_DEMAND_BACKEND = "shopman.craftsman.contrib.demand.backend.OrderingDemandBackend"

All settings have sensible defaults — zero configuration required.

INVENTORY_BACKEND is a read-only seam for ingredient-availability guardrails
(over-plan on adjust, missing-on-finish, shortage status on suggestions). Stock
ledger writes are NOT done through it — they flow through the production_changed
signal handlers in contrib.stockman.

Default None here (standalone Craftsman = guardrails dormant). The orchestrator
wires it to shopman.shop.adapters.inventory.InventoryAvailabilityBackend (Buyman
WP-B5b), and the seed gives ingredients real Stockman stock so the guardrails
have something to check. With a real backend, adjust()/finish() validate that the
recipe's ingredients are on hand (insufficient → INSUFFICIENT_MATERIALS).

SCALE_PRECISION_G, MIXER_LOSS_G e YIELD_MARGIN_SIGMAS orçam a margem de
segurança do rendimento das massas — a conta de "quanto de massa fazer" para N
peças numa balança de divisão finita. São decisão de PRODUÇÃO, não de ficha: a
ficha diz a proporção, a margem diz quanto se faz. Ver
``shopman.craftsman.services.yield_margin`` para a aritmética e para o motivo
de o excesso esperado por peça ser meia divisão, e não uma.
"""

from decimal import Decimal

from django.conf import settings

# ── Defaults ──

DEFAULTS = {
    # "graceful" (default): backend failures log warning and continue.
    # "strict": backend failures abort the operation with CraftError.
    "MODE": "graceful",
    "INVENTORY_BACKEND": None,
    "CATALOG_BACKEND": None,
    "DEMAND_BACKEND": None,
    # Dotted path to a callable returning [(value, label), ...] for the
    # Recipe.meta["production_lifecycle"] admin field. The orchestrator that
    # dispatches production lifecycles provides it; unset = field hidden
    # (Craftsman itself has no lifecycle concept).
    "PRODUCTION_LIFECYCLE_PROVIDER": None,
    "SAFETY_STOCK_PERCENT": Decimal("0.20"),
    "HISTORICAL_DAYS": 28,
    "SAME_WEEKDAY_ONLY": True,
    "FORMULA_FACTOR_PROVIDERS": [],
    "FORMULA_ROUNDING_MULTIPLE": None,
    "FORMULA_CAPACITY_PROVIDER": None,
    # ── Margem de rendimento das massas (ver services/yield_margin.py) ──
    # Divisão da balança de bancada, em gramas. É propriedade do EQUIPAMENTO
    # (uma balança serve todas as fichas), por isso settings e não Recipe.meta.
    # A casa usa balança de 2 g; trocar a balança é trocar esta linha.
    "SCALE_PRECISION_G": Decimal("2"),
    # Perda da masseira por fornada, em gramas — o filme que fica na bacia.
    # Padrão CONSERVADOR e **estimativa não auditada**: existe para a conta não
    # parar. Cada ficha declara a sua em Recipe.meta["mixer_loss_g"], e o passo
    # seguinte é o sistema APRENDER a real (produzido menos consumido, que o
    # ledger já sabe) em vez de manter um chute cadastrado.
    "MIXER_LOSS_G": Decimal("150"),
    # Colchão de variância, em desvios-padrão da SOMA dos arredondamentos
    # (d·√(N/12)). Três desvios cobrem a cauda; o colchão encolhe em proporção
    # quando a fornada cresce, porque √N cresce mais devagar que N.
    "YIELD_MARGIN_SIGMAS": Decimal("3"),
}


# ── Accessors ──

_sentinel = object()


def get_setting(name, default=_sentinel):
    """
    Get a crafting setting.

    Looks up in order:
    1. CRAFTSMAN dict (e.g. CRAFTSMAN = {"INVENTORY_BACKEND": "..."})
    2. Flat setting (e.g. CRAFTSMAN_INVENTORY_BACKEND = "...")
    3. DEFAULTS
    """
    crafting_dict = getattr(settings, "CRAFTSMAN", {})
    if name in crafting_dict:
        return crafting_dict[name]

    flat_value = getattr(settings, f"CRAFTSMAN_{name}", _sentinel)
    if flat_value is not _sentinel:
        return flat_value

    if default is not _sentinel:
        return default

    return DEFAULTS.get(name)
