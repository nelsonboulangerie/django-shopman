"""Máquina de estados do episódio (v2 5.7, sem mudança).

Toda transição: confere a versão que quem decidiu viu, incrementa a versão e
devolve um registro ``Episode`` NOVO (o anterior fica como estava, N14). Toda
espera tem condição de retomada, responsável e prazo, e entrar num estado de
espera sem ela é recusa. A época de posse só cresce: muda a cada troca de dono,
e é o que torna recusáveis os comandos antigos da automação (N10).

| De | Evento | Para |
|---|---|---|
| active | question_sent | waiting_input |
| waiting_input | evidence_arrived | active |
| active | terms_presented | waiting_authorization |
| waiting_authorization | grant_valid | active (para reconferir e executar) |
| waiting_authorization | authorization_invalidated | active (invalida a autorização pendente) |
| active | command_handed_off | waiting_effect |
| waiting_effect | receipt_terminal | active |
| waiting_effect | receipt_open | waiting_effect (agenda reconciliação) |
| waiting_effect | reconciliation_overdue | awaiting_handoff (vencido o prazo, pessoa) |
| qualquer não resolvido | handoff_requested | awaiting_handoff (revoga a posse da automação) |
| awaiting_handoff | handoff_accepted | human_owned |
| awaiting_handoff | handoff_not_accepted | awaiting_handoff (contingência; nada afirma aceite) |
| human_owned | returned | active (posse nova, pergunta antiga invalidada) |
| active, human_owned | resolved | resolved (com evidência) |
| resolved | reopened | active (evento de reabertura) |
"""

from __future__ import annotations

import dataclasses
import re
import typing
from dataclasses import dataclass
from typing import Literal

from conversational_commerce.contracts import Commitment, Episode, Need, Ownership, Wait
from conversational_commerce.contracts.common import Rule
from conversational_commerce.contracts.validate import PATTERNS

from .errors import InvalidTransition, StaleVersion

INSTANT = re.compile(PATTERNS[Rule.INSTANT])

EventKind = Literal[
    "question_sent",
    "evidence_arrived",
    "terms_presented",
    "grant_valid",
    "authorization_invalidated",
    "command_handed_off",
    "receipt_terminal",
    "receipt_open",
    "reconciliation_overdue",
    "handoff_requested",
    "handoff_accepted",
    "handoff_not_accepted",
    "returned",
    "resolved",
    "reopened",
]

UNRESOLVED = ("active", "waiting_input", "waiting_authorization", "waiting_effect", "awaiting_handoff", "human_owned")

# (estado, evento) → próximo estado. ``handoff_requested`` vale de todo estado não resolvido.
TABLE: dict[tuple[str, str], str] = {
    ("active", "question_sent"): "waiting_input",
    ("waiting_input", "evidence_arrived"): "active",
    ("active", "terms_presented"): "waiting_authorization",
    ("waiting_authorization", "grant_valid"): "active",
    ("waiting_authorization", "authorization_invalidated"): "active",
    ("active", "command_handed_off"): "waiting_effect",
    ("waiting_effect", "receipt_terminal"): "active",
    ("waiting_effect", "receipt_open"): "waiting_effect",
    ("waiting_effect", "reconciliation_overdue"): "awaiting_handoff",
    ("awaiting_handoff", "handoff_accepted"): "human_owned",
    ("awaiting_handoff", "handoff_not_accepted"): "awaiting_handoff",
    ("human_owned", "returned"): "active",
    ("active", "resolved"): "resolved",
    ("human_owned", "resolved"): "resolved",
    ("resolved", "reopened"): "active",
    **{(state, "handoff_requested"): "awaiting_handoff" for state in UNRESOLVED if state != "awaiting_handoff"},
}

# Eventos que entram (ou permanecem) numa espera: exigem a espera completa.
NEEDS_WAIT = frozenset({"question_sent", "terms_presented", "command_handed_off", "receipt_open",
                        "reconciliation_overdue", "handoff_requested", "handoff_not_accepted"})
# Eventos que trocam o dono: a época sobe.
OWNER_CHANGE = {"reconciliation_overdue": "queue", "handoff_requested": "queue", "handoff_accepted": "person",
                "returned": "automation"}


@dataclass(frozen=True, slots=True)
class EpisodeEvent:
    """O que aconteceu, com o que a transição exige.

    ``wait``: a espera em que o episódio entra (condição, responsável, prazo).
    ``holder_ref``: quem aceitou (``handoff_accepted``).
    ``needs`` e ``commitments``: a evidência de resolução (``resolved``).

    Carrega registros (``Need``, ``Commitment``), por isso não é um ``Value`` de
    contrato: a conferência é feita aqui.
    """

    kind: EventKind
    at: str
    cause_id: str
    wait: Wait | None = None
    holder_ref: str | None = None
    needs: tuple[Need, ...] = ()
    commitments: tuple[Commitment, ...] = ()

    def __post_init__(self) -> None:
        if self.kind not in typing.get_args(EventKind):
            raise ValueError(f"evento de episódio desconhecido: {self.kind!r}")
        if not INSTANT.fullmatch(self.at):
            raise ValueError(f"instante fora da forma canônica: {self.at!r}")
        if not self.cause_id:
            raise ValueError("evento sem causa")
        if self.wait is not None and not isinstance(self.wait, Wait):
            raise TypeError("wait precisa ser um Wait")
        object.__setattr__(self, "needs", tuple(self.needs))
        object.__setattr__(self, "commitments", tuple(self.commitments))
        if not all(isinstance(n, Need) for n in self.needs) or not all(
                isinstance(c, Commitment) for c in self.commitments):
            raise TypeError("needs e commitments são registros Need e Commitment")


def next_state(state: str, kind: str) -> str | None:
    return TABLE.get((state, kind))


def _check_resolution(episode: Episode, event: EpisodeEvent) -> None:
    """Resolver exige evidência: toda necessidade satisfeita ou retirada, todo compromisso cumprido."""
    reported = {need.need_id: need for need in event.needs}
    missing = sorted(set(episode.needs) - set(reported))
    if missing:
        raise InvalidTransition(episode.state, event.kind, f"necessidade sem estado informado: {missing}")
    open_needs = sorted(n.need_id for n in event.needs if n.state not in ("satisfied", "withdrawn"))
    if open_needs:
        raise InvalidTransition(episode.state, event.kind, f"necessidade aberta: {open_needs}")
    open_commitments = sorted(c.commitment_id for c in event.commitments if c.state != "fulfilled")
    if open_commitments:
        raise InvalidTransition(episode.state, event.kind, f"compromisso não cumprido: {open_commitments}")


def transition(episode: Episode, event: EpisodeEvent, *, expected_version: int, record_id: str) -> Episode:
    """Aplica ``event`` e devolve o registro novo do episódio (versão + 1)."""
    if expected_version != episode.version:
        raise StaleVersion(expected_version, episode.version)
    target = next_state(episode.state, event.kind)
    if target is None:
        raise InvalidTransition(episode.state, event.kind, "transição inexistente na máquina do episódio")
    if event.at < episode.occurred_at:
        raise InvalidTransition(episode.state, event.kind, "evento anterior ao estado atual")
    if event.kind in NEEDS_WAIT:
        if event.wait is None:
            raise InvalidTransition(episode.state, event.kind, "espera sem condição, responsável e prazo")
        if event.wait.deadline <= event.at:
            raise InvalidTransition(episode.state, event.kind, "espera com prazo vencido")
    if event.kind == "resolved":
        _check_resolution(episode, event)

    ownership = episode.ownership
    new_owner = OWNER_CHANGE.get(event.kind)
    if new_owner is not None:
        if new_owner == "person" and event.holder_ref is None:
            raise InvalidTransition(episode.state, event.kind, "aceite é nominal: diga quem aceitou")
        ownership = Ownership(owner=new_owner, epoch=ownership.epoch + 1,
                              holder_ref=None if new_owner == "automation" else event.holder_ref)

    waits = (event.wait,) if event.wait is not None and event.kind in NEEDS_WAIT else ()
    changes = {
        "id": record_id,
        "cause_id": event.cause_id,
        "occurred_at": event.at,
        "recorded_at": None,
        "state": target,
        "version": episode.version + 1,
        "ownership": ownership,
        "waits": waits,
        "resolved_at": event.at if target == "resolved" else None,
    }
    if event.kind == "reopened":
        changes["reopened_from"] = episode.id
    return dataclasses.replace(episode, **changes)


def open_episode(*, record_id: str, episode_id: str, tenant: str, environment: str, trace_id: str, at: str,
                 producer, subject: str | None, needs: tuple[str, ...] = ()) -> Episode:
    """Episódio novo: ``active``, versão 1, posse da automação na época 0."""
    return Episode(id=record_id, tenant=tenant, environment=environment, trace_id=trace_id, occurred_at=at,
                   producer=producer, episode_id=episode_id, subject=subject, state="active", version=1,
                   ownership={"owner": "automation", "epoch": 0}, needs=needs, opened_at=at)
