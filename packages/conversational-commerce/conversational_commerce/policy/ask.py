"""Quando perguntar, e quando cobrir as duas leituras (v2 4.2).

Para duas interpretações, com ``p`` a probabilidade da mais provável, ``L`` o
custo de agir errado e ``c`` o custo de perguntar::

    pergunta  ⇔  (1 − p) · L > c

Ressalvas que valem desde o primeiro dia: campo obrigatório e dado de
segurança SEMPRE se perguntam, sem cálculo; sem estimativa confiável, vale a
regra pelo custo do erro: na dúvida sobre uma MUDANÇA (L alto) pergunta; na
dúvida sobre uma CONSULTA (L é uma mensagem a mais) responde as duas leituras.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal


@dataclass(frozen=True, slots=True)
class AskEconomics:
    """Estimativas para a regra de custo. Decimal em texto, nunca float."""

    top_probability: str
    loss_if_wrong: str
    cost_of_asking: str

    def __post_init__(self) -> None:
        p = Decimal(self.top_probability)
        if not (0 <= p <= 1):
            raise ValueError("top_probability fora de [0, 1]")
        if Decimal(self.loss_if_wrong) < 0 or Decimal(self.cost_of_asking) < 0:
            raise ValueError("custos não negativos")


Resolution = Literal["act", "ask", "cover_both"]


def resolve_ambiguity(*, request_kind: str, reading_count: int, missing_required_field: bool,
                      economics: AskEconomics | None = None) -> Resolution:
    """O que fazer com o pedido: agir na leitura única, perguntar, ou cobrir as duas leituras."""
    if missing_required_field:
        return "ask"
    if reading_count < 2:
        return "act"
    if request_kind == "query":
        return "cover_both"
    if economics is None:
        return "ask"  # mudança sem estimativa: pergunta
    p = Decimal(economics.top_probability)
    expected_loss = (1 - p) * Decimal(economics.loss_if_wrong)
    return "ask" if expected_loss > Decimal(economics.cost_of_asking) else "act"
