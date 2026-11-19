"""``decide``: a política pura (v2 4.1 a 4.3). Admissível, prioritário, melhor.

1. **Admissibilidade:** cada proposta é avaliada no catálogo (F2): toda
   precondição em ``pass``; ``unknown`` bloqueia a ação, não o sistema.
   Movimento fora do catálogo nunca é executável.
2. **Ambiguidade (v2 4.2):** duas leituras numa mudança bloqueiam a ação de
   nível A2 ou acima (pergunta-se antes); numa consulta, bloqueiam a resposta
   de uma leitura só (cobrem-se as duas).
3. **Prioridade:** por necessidade, a família que vence; uma mensagem com
   reclamação e dúvida são duas necessidades, e o plano atende as duas.
   Problema aberto suspende o comércio; transferência suspende mudança de
   pedido; no máximo uma iniciativa comercial por decisão.
4. **Escolha:** na família vencedora, ordem estável do catálogo
   (determinística), ou sorteio com semente quando o perfil o liga.

Função pura: sem relógio, sem id gerado aqui, sem porta. Mesmas entradas,
mesmo registro (K40).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from conversational_commerce.catalog import MOVES, Situation, evaluate_move
from conversational_commerce.catalog.levels import authority_rank
from conversational_commerce.catalog.moves import CATALOG
from conversational_commerce.contracts import (
    ContextSnapshot,
    DecisionRecord,
    DeploymentProfile,
    Producer,
)
from conversational_commerce.profile import read_line

from .ask import AskEconomics, resolve_ambiguity
from .selection import decimal_text, seeded_pick, uniform_weights

POLICY_ID = "moves"
POLICY_VERSION = "1"
SEEDED_LINE = "policy.seeded_selection"
CATALOG_ORDER = {move.name: index for index, move in enumerate(CATALOG)}
NO_ESTIMATOR = {"status": "unavailable", "reason": "no_estimator"}
# Movimentos que respondem uma leitura só: numa consulta ambígua, cedem a ``cover_readings``.
SINGLE_READING_ANSWERS = frozenset({"inform"})


@dataclass(frozen=True, slots=True)
class Proposal:
    """Uma candidata proposta pelo turno, com a situação que as precondições leem."""

    candidate_ref: str
    need_id: str
    move: str
    content: Mapping[str, Any]
    situation: Situation
    economics: AskEconomics | None = None


@dataclass(frozen=True, slots=True)
class DecisionInput:
    decision_id: str
    record_id: str
    trace_id: str
    occurred_at: str
    turn: int
    snapshot: ContextSnapshot
    profile: DeploymentProfile
    proposals: tuple[Proposal, ...]
    producer: Producer = field(default_factory=lambda: Producer(name="conversational-commerce", version="policy-1"))
    seed: str | None = None
    parent_decision_id: str | None = None


@dataclass
class _Row:
    proposal: Proposal
    blocked: list[str]

    @property
    def eligible(self) -> bool:
        return not self.blocked

    def block(self, reason: str) -> None:
        if reason not in self.blocked:
            self.blocked.append(reason)

    def family(self) -> str | None:
        move = MOVES.get(self.proposal.move)
        return None if move is None else move.family

    def rank(self) -> tuple[int, int]:
        move = MOVES[self.proposal.move]
        return move.family_rank(), CATALOG_ORDER[move.name]


def _admissibility(inp: DecisionInput) -> list[_Row]:
    rows = []
    for proposal in inp.proposals:
        if proposal.move not in MOVES:
            rows.append(_Row(proposal, ["move_outside_catalog"]))
            continue
        evaluation = evaluate_move(proposal.move, proposal.situation, inp.profile)
        rows.append(_Row(proposal, list(evaluation.blocked_by)))
    return rows


def _ambiguity(rows: list[_Row]) -> None:
    for row in rows:
        if row.proposal.move not in MOVES:
            continue
        s = row.proposal.situation
        if s.request_kind is None or s.reading_count is None or s.missing_required_field is None:
            continue  # as precondições já marcaram o desconhecido
        resolution = resolve_ambiguity(request_kind=s.request_kind, reading_count=s.reading_count,
                                       missing_required_field=s.missing_required_field,
                                       economics=row.proposal.economics)
        move = MOVES[row.proposal.move]
        if resolution == "ask" and authority_rank(move.authority) >= authority_rank("A2"):
            row.block("ambiguous_change_ask_first")
        if resolution == "cover_both" and move.name in SINGLE_READING_ANSWERS:
            row.block("two_readings_cover_both")


def _winners(rows: list[_Row]) -> dict[str, _Row]:
    winners: dict[str, _Row] = {}
    for row in rows:
        if not row.eligible:
            continue
        need = row.proposal.need_id
        if need not in winners or row.rank() < winners[need].rank():
            winners[need] = row
    return winners


def _suspensions(rows: list[_Row]) -> dict[str, _Row]:
    """Aplica as suspensões entre necessidades até estabilizar."""
    while True:
        winners = _winners(rows)
        changed = False
        families = {row.family() for row in winners.values()}
        handoff = any(row.proposal.move == "handoff" for row in winners.values())
        for row in rows:
            if not row.eligible:
                continue
            move = MOVES[row.proposal.move]
            if "protect_and_fulfill" in families and move.family == "commerce":
                row.block("suspended_by_open_problem")
                changed = True
            elif handoff and row.proposal.move != "handoff" and authority_rank(move.authority) >= authority_rank("A2"):
                row.block("suspended_by_handoff")
                changed = True
        commerce = sorted((r for r in winners.values() if r.family() == "commerce"),
                          key=lambda r: (r.rank(), r.proposal.need_id))
        for extra in commerce[1:]:
            extra.block("one_commercial_initiative")
            changed = True
        if not changed:
            return winners


def _selection(inp: DecisionInput, rows: list[_Row], winners: dict[str, _Row]) -> tuple[list[int], dict[str, Any]]:
    index_of = {id(row): index for index, row in enumerate(rows)}
    if inp.seed is None:
        chosen = sorted(index_of[id(row)] for row in winners.values())
        return chosen, {"method": "deterministic", "tie_break": "catalog_order",
                        "propensity": {"status": "not_applicable"}}
    reading = read_line(inp.profile, SEEDED_LINE)
    if not reading.usable or reading.value is not True:
        raise ValueError("seleção sorteada exige a linha policy.seeded_selection aprovada")
    if len(winners) != 1:
        raise ValueError("seleção sorteada no D1 decide uma necessidade por vez")
    (winner,) = winners.values()
    family = winner.family()
    pool = sorted((row for row in rows if row.eligible and row.proposal.need_id == winner.proposal.need_id
                   and row.family() == family), key=lambda row: row.rank())
    weights = uniform_weights(len(pool))
    picked = pool[seeded_pick(inp.seed, weights)]
    return [index_of[id(picked)]], {
        "method": "seeded",
        "propensity": {
            "status": "recorded",
            "seed": inp.seed,
            "distribution": [{"candidate": index_of[id(row)], "probability": decimal_text(weight)}
                             for row, weight in zip(pool, weights, strict=True)],
            "executed_probability": decimal_text(weights[pool.index(picked)]),
        },
    }


def decide(inp: DecisionInput) -> DecisionRecord:
    """A decisão do turno: candidatas, bloqueios, escolha e seleção, num registro imutável."""
    if inp.snapshot.hash is None:
        raise ValueError("a decisão aponta um snapshot selado")
    rows = _admissibility(inp)
    _ambiguity(rows)
    winners = _suspensions(rows)
    chosen, selection = _selection(inp, rows, winners)
    return DecisionRecord(
        id=inp.record_id,
        tenant=inp.snapshot.tenant,
        environment=inp.snapshot.environment,
        trace_id=inp.trace_id,
        cause_id=inp.snapshot.id,
        occurred_at=inp.occurred_at,
        producer=inp.producer,
        episode_id=inp.snapshot.episode_id,
        decision_id=inp.decision_id,
        turn=inp.turn,
        context={"snapshot_ref": inp.snapshot.id, "snapshot_hash": inp.snapshot.hash},
        candidates=[
            {"candidate_ref": row.proposal.candidate_ref, "need_id": row.proposal.need_id, "move": row.proposal.move,
             "content": dict(row.proposal.content), "eligible": row.eligible, "blocked_by": row.blocked,
             "prediction": NO_ESTIMATOR}
            for row in rows
        ],
        chosen=chosen,
        selection=selection,
        policy={"id": POLICY_ID, "version": POLICY_VERSION},
        profile={"id": inp.profile.id, "version": inp.profile.version},
        parent_decision_id=inp.parent_decision_id,
    )
