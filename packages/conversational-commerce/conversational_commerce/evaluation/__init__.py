"""Avaliação: o trilho de economia (v2 8.5) e o placar de conversa (o cliente foi atendido?)."""

from .conversation import OUTCOMES, IncumbentProfile, Scorecard, TurnEvidence, incumbent_reach, outcome_of, score
from .economics import Comparison, compare_costs

__all__ = [
    "OUTCOMES",
    "Comparison",
    "IncumbentProfile",
    "Scorecard",
    "TurnEvidence",
    "compare_costs",
    "incumbent_reach",
    "outcome_of",
    "score",
]
