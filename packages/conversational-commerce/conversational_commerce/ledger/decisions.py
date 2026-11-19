"""O livro das decisões: só acrescenta. Bloqueio depois da decisão gera decisão NOVA ligada.

N14 e N17: a decisão registra candidatas, bloqueios e o método de seleção, e não
se reescreve. Se uma guarda posterior bloqueia a ação escolhida (K32), grava-se
outra decisão com ``parent_decision_id`` apontando a anterior: a candidata
bloqueada aparece inelegível com o motivo, a substituta é escolhida pela ordem
estável do catálogo, e a probabilidade do sorteio original NÃO é atribuída a
ela (``propensity: not_applicable``).
"""

from __future__ import annotations

import dataclasses

from conversational_commerce.catalog import MOVES
from conversational_commerce.catalog.moves import CATALOG
from conversational_commerce.contracts import DecisionCandidate, DecisionRecord

CATALOG_ORDER = {move.name: index for index, move in enumerate(CATALOG)}


class LedgerError(ValueError):
    pass


class DecisionLedger:
    """Decisões em ordem de gravação. Mesmo ``decision_id`` duas vezes é recusa."""

    def __init__(self) -> None:
        self._by_id: dict[str, DecisionRecord] = {}
        self._order: list[str] = []

    def append(self, record: DecisionRecord) -> DecisionRecord:
        if record.decision_id in self._by_id:
            raise LedgerError(f"decisão já gravada: {record.decision_id}; correção é decisão nova")
        if record.parent_decision_id is not None and record.parent_decision_id not in self._by_id:
            raise LedgerError(f"decisão mãe desconhecida: {record.parent_decision_id}")
        self._by_id[record.decision_id] = record
        self._order.append(record.decision_id)
        return record

    def get(self, decision_id: str) -> DecisionRecord:
        return self._by_id[decision_id]

    def __len__(self) -> int:
        return len(self._order)

    def lineage(self, decision_id: str) -> list[DecisionRecord]:
        """Da decisão original até ``decision_id``."""
        chain = []
        current: str | None = decision_id
        while current is not None:
            record = self._by_id[current]
            chain.append(record)
            current = record.parent_decision_id
        return list(reversed(chain))


def _rank(candidate: DecisionCandidate) -> tuple[int, int]:
    move = MOVES[candidate.move]
    return move.family_rank(), CATALOG_ORDER[move.name]


def redecide_after_block(previous: DecisionRecord, *, blocked_candidate_ref: str, reason: str, decision_id: str,
                         record_id: str, occurred_at: str) -> DecisionRecord:
    """A decisão nova, ligada, depois que uma guarda bloqueou a ação escolhida."""
    positions = [i for i, c in enumerate(previous.candidates) if c.candidate_ref == blocked_candidate_ref]
    if not positions:
        raise LedgerError(f"candidata desconhecida: {blocked_candidate_ref}")
    blocked_index = positions[0]
    if blocked_index not in previous.chosen:
        raise LedgerError("só se bloqueia depois o que foi escolhido")
    candidates = list(previous.candidates)
    blocked = candidates[blocked_index]
    candidates[blocked_index] = dataclasses.replace(blocked, eligible=False, blocked_by=(*blocked.blocked_by, reason))
    chosen = [index for index in previous.chosen if index != blocked_index]
    same_need = [i for i, c in enumerate(candidates) if c.eligible and c.need_id == blocked.need_id
                 and c.move in MOVES and i not in chosen]
    if same_need:
        chosen.append(min(same_need, key=lambda i: _rank(candidates[i])))
    return dataclasses.replace(
        previous,
        id=record_id,
        decision_id=decision_id,
        occurred_at=occurred_at,
        recorded_at=None,
        cause_id=previous.id,
        candidates=candidates,
        chosen=sorted(chosen),
        selection={"method": "deterministic", "tie_break": "catalog_order",
                   "propensity": {"status": "not_applicable"}},
        parent_decision_id=previous.decision_id,
    )
