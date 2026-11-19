"""Política pura: admissível, prioritário, melhor (F5). Especificação: ``spec/05-policy.md``."""

from .advisor import adheres_to_declared_need
from .ask import AskEconomics, resolve_ambiguity
from .decide import POLICY_ID, POLICY_VERSION, DecisionInput, Proposal, decide
from .selection import decimal_text, seeded_pick, uniform_weights

__all__ = [
    "POLICY_ID",
    "POLICY_VERSION",
    "AskEconomics",
    "DecisionInput",
    "Proposal",
    "adheres_to_declared_need",
    "decide",
    "decimal_text",
    "resolve_ambiguity",
    "seeded_pick",
    "uniform_weights",
]
