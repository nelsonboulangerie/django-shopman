"""Escolha dentro da família vencedora: determinística (D1) ou sorteada com semente.

No D1 nenhum termo de ``Q(b, a)`` tem estimador, então a escolha é pela ordem
estável do catálogo, e o registro diz ``method: deterministic``,
``propensity: not_applicable`` (nunca "probabilidade 1").

[DIVERGE, plano 3.5] ``seeded`` existe no D1 só para provar K32 e K40: sorteio
uniforme entre as elegíveis da família vencedora, com a semente registrada, a
distribuição DEPOIS dos filtros e a probabilidade da ação executada. Só com a
linha de perfil ``policy.seeded_selection`` aprovada. Não é o bandit do D6.
"""

from __future__ import annotations

import random
from collections.abc import Sequence
from decimal import ROUND_DOWN, Decimal

SCALE = Decimal("0.0001")


def decimal_text(value: Decimal) -> str:
    """Decimal na forma normalizada do F1 (sem zero à direita, sem expoente)."""
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return "0" if text in ("-0", "") else text


def uniform_weights(count: int) -> list[Decimal]:
    """Pesos iguais em quatro casas, somando exatamente 1 (o resto vai para o primeiro)."""
    if count < 1:
        raise ValueError("distribuição vazia")
    share = (Decimal(1) / count).quantize(SCALE, rounding=ROUND_DOWN)
    weights = [share] * count
    weights[0] += Decimal(1) - share * count
    return weights


def seeded_pick(seed: str, weights: Sequence[Decimal]) -> int:
    """O índice sorteado. Mesma semente e mesmos pesos, mesmo índice (K40)."""
    draw = Decimal(str(random.Random(seed).random()))
    cumulative = Decimal(0)
    for index, weight in enumerate(weights):
        cumulative += weight
        if draw < cumulative:
            return index
    return len(weights) - 1
