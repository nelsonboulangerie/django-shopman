"""Necessidades dentro do episódio (v2 5.7).

*Satisfeita* exige evidência (fato entregue, recibo, cumprimento); *retirada*
exige ato do cliente ou regra do perfil, nunca silêncio; uma necessidade
bloqueada segura as que dependem dela. Uma reclamação não apaga a dúvida que
veio na mesma mensagem: cada uma é uma necessidade.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Iterable
from typing import Literal

from conversational_commerce.contracts import Need

from .errors import InvalidTransition

NEED_TRANSITIONS: dict[str, frozenset[str]] = {
    "open": frozenset({"blocked", "satisfied", "withdrawn"}),
    "blocked": frozenset({"open", "withdrawn"}),
    "satisfied": frozenset({"open"}),  # a mesma necessidade volta
    "withdrawn": frozenset({"open"}),
}

WithdrawnBy = Literal["customer_act", "profile_rule"]


def update_need(need: Need, state: str, *, record_id: str, at: str, evidence: Iterable[str] = (),
                withdrawn_by: WithdrawnBy | None = None) -> Need:
    """O registro novo da necessidade em ``state``."""
    if state not in NEED_TRANSITIONS[need.state]:
        raise InvalidTransition(need.state, state, "transição de necessidade inexistente")
    new_evidence = tuple(evidence)
    if state == "satisfied" and not new_evidence:
        raise InvalidTransition(need.state, state, "satisfeita exige evidência nova")
    if state == "withdrawn":
        if withdrawn_by is None:
            raise InvalidTransition(need.state, state, "retirada exige ato do cliente ou regra do perfil, nunca silêncio")
        if not new_evidence:
            raise InvalidTransition(need.state, state, "retirada aponta o ato ou a regra")
    return dataclasses.replace(need, id=record_id, occurred_at=at, recorded_at=None, state=state,
                               evidence=(*need.evidence, *new_evidence) if state != "open" else ())


def held_by_blocked(needs: Iterable[Need]) -> frozenset[str]:
    """As necessidades seguradas por uma bloqueada, direta ou indiretamente."""
    by_id = {need.need_id: need for need in needs}
    blocked = {need_id for need_id, need in by_id.items() if need.state == "blocked"}
    held: set[str] = set()
    changed = True
    while changed:
        changed = False
        for need_id, need in by_id.items():
            if need_id in held or need_id in blocked:
                continue
            if any(dep in blocked or dep in held for dep in need.depends_on):
                held.add(need_id)
                changed = True
    return frozenset(held)


def actionable(needs: Iterable[Need]) -> tuple[Need, ...]:
    """As abertas que não estão seguradas: é com elas que o turno trabalha."""
    needs = tuple(needs)
    held = held_by_blocked(needs)
    return tuple(need for need in needs if need.state == "open" and need.need_id not in held)
