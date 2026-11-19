"""Catálogo de movimentos v1, níveis de autoridade e a avaliação de precondições.

Especificação: ``spec/02-catalog-profile.md``.
"""

from .evaluate import MoveEvaluation, evaluate_catalog, evaluate_move
from .levels import AUTOMATION_FORBIDDEN, at_least_identity, requires_confirmation, stricter_authority
from .moves import CATALOG, FAMILIES, MOVES, Move
from .preconditions import GENERIC, SPECIFIC, Precondition
from .situation import Situation

__all__ = [
    "AUTOMATION_FORBIDDEN",
    "CATALOG",
    "FAMILIES",
    "GENERIC",
    "MOVES",
    "SPECIFIC",
    "Move",
    "MoveEvaluation",
    "Precondition",
    "Situation",
    "at_least_identity",
    "evaluate_catalog",
    "evaluate_move",
    "requires_confirmation",
    "stricter_authority",
]
