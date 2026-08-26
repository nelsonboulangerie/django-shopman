"""
Django Craftsman — Headless Micro-MRP Framework (vNext).

5 models, 5 verbs, 4 states. Cabe na cabeca.

Usage:
    from shopman.craftsman import craft, CraftError

    wo = craft.plan(recipe, 100)
    craft.start(wo, quantity=97)
    craft.finish(wo, finished=95)

    wo.started_qty   # 97
    wo.finished_qty  # 95
    wo.loss          # 2
    wo.yield_rate    # 0.9793...
    wo.events.all()  # [planned, started, finished]

Philosophy: SIREL (Simples, Robusto, Elegante)
"""

from shopman.craftsman.exceptions import CraftError, StaleRevision


def __getattr__(name):
    """Lazy import to avoid AppRegistryNotReady errors."""
    if name in ("craft", "CraftService"):
        from shopman.craftsman.service import CraftService

        return CraftService
    if name == "suggest":
        from shopman.craftsman.contrib.formula import suggest

        return suggest
    if name == "OrderingDemandBackend":
        # Backend de demanda de referência (lê pedidos). Já é público de fato:
        # é o valor de DEMAND_BACKEND que a instância aponta e o ponto de
        # partida de quem compõe um backend próprio.
        from shopman.craftsman.contrib.demand.backend import OrderingDemandBackend

        return OrderingDemandBackend
    if name in (
        "realize_finished_production",
        "stock_legs_complete",
        "STOCK_CONSUMED_KEY",
        "STOCK_REALIZED_KEY",
        "STARTED_BATCH",
    ):
        # API de recuperação da ponte craftsman→stockman. O `finish` emite o
        # signal FORA do atomic, então uma queda no meio do handler deixa a
        # fornada concluída com o ledger pela metade; quem varre precisa saber
        # ler os marcadores por perna e refazer o que faltou.
        from shopman.craftsman.contrib.stockman import handlers

        return getattr(handlers, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "craft",
    "CraftService",
    "CraftError",
    "StaleRevision",
    "suggest",
    "OrderingDemandBackend",
    "realize_finished_production",
    "stock_legs_complete",
    "STOCK_CONSUMED_KEY",
    "STOCK_REALIZED_KEY",
    "STARTED_BATCH",
]
__version__ = "0.3.0"
