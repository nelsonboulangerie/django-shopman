"""Comparação econômica de alternativas, vetada quando falta o custo (K34, N21).

Modelo sem preço cadastrado tem custo **desconhecido**, nunca zero. Comparar o que
custa com o que não se sabe quanto custa daria vantagem a quem não declarou
preço: a comparação é vetada, com motivo, até que todo braço tenha custo
conhecido na mesma moeda.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Literal

from conversational_commerce.ports.model import KnownCost


@dataclass(frozen=True, slots=True)
class Comparison:
    status: Literal["compared", "vetoed"]
    reason: str | None = None
    # Braço → custo total em unidades menores, quando comparado.
    totals: Mapping[str, int] | None = None
    cheapest: str | None = None


def compare_costs(arms: Mapping[str, Iterable]) -> Comparison:
    """``arms``: braço → consumos (``ports.Consumption``). Vetada se algum custo é desconhecido."""
    totals: dict[str, int] = {}
    currency = None
    for arm, consumptions in arms.items():
        total = 0
        for consumption in consumptions:
            cost = consumption.cost
            if not isinstance(cost, KnownCost):
                return Comparison("vetoed", reason=f"cost_unknown:{arm}")
            if currency is None:
                currency = cost.amount.currency
            elif cost.amount.currency != currency:
                return Comparison("vetoed", reason="currency_mismatch")
            total += cost.amount.amount_minor
        totals[arm] = total
    if not totals:
        return Comparison("vetoed", reason="no_arms")
    cheapest = min(sorted(totals), key=lambda arm: totals[arm])
    return Comparison("compared", totals=totals, cheapest=cheapest)
