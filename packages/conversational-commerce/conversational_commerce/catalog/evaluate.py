"""Avaliação de um movimento numa situação, sob um perfil.

``evaluate_move`` avalia TODAS as precondições (não para na primeira), para que
a decisão registre cada bloqueio (N17). Elegível só com todas em ``pass``; uma
``fail`` ou uma ``unknown`` bloqueia. Escolher entre elegíveis é do F5.
"""

from __future__ import annotations

from dataclasses import dataclass

from conversational_commerce.contracts import DeploymentProfile, PreconditionResult
from conversational_commerce.profile.codes import unknown_code

from .moves import MOVES, Move
from .situation import Situation


@dataclass(frozen=True, slots=True)
class MoveEvaluation:
    move: str
    results: tuple[PreconditionResult, ...]
    eligible: bool
    # Códigos de bloqueio, na ordem das precondições, sem repetição.
    blocked_by: tuple[str, ...]


def evaluate_move(move: Move | str, situation: Situation, profile: DeploymentProfile) -> MoveEvaluation:
    if isinstance(move, str):
        if move not in MOVES:
            raise KeyError(f"movimento fora do catálogo: {move!r}")
        move = MOVES[move]
    results = []
    blocked: list[str] = []
    for precondition in move.preconditions:
        if any(getattr(situation, field) is None for field in precondition.reads):
            code = unknown_code(precondition.code)
            results.append(PreconditionResult(code=precondition.code, result="unknown", evidence={"reason": code}))
            reason = code
        else:
            failure = precondition.check(situation, profile, move)
            if failure is None:
                results.append(PreconditionResult(code=precondition.code, result="pass"))
                continue
            reason = str(failure)
            results.append(PreconditionResult(code=precondition.code, result="fail", evidence={"reason": reason}))
        if reason not in blocked:
            blocked.append(reason)
    return MoveEvaluation(move.name, tuple(results), not blocked, tuple(blocked))


def evaluate_catalog(situation: Situation, profile: DeploymentProfile) -> tuple[MoveEvaluation, ...]:
    """Todos os movimentos do catálogo, na ordem do catálogo."""
    return tuple(evaluate_move(move, situation, profile) for move in MOVES.values())
