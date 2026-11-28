"""O livro dos compromissos: promessa e caso numa forma só, que só acrescenta (v2 4.6).

O compromisso é o que a casa ficou devendo. Reconhecer, aceitar e cumprir são
eventos distintos: encaminhar não é aceitar, e aceitar não é cumprir.

| De | Para | Quando |
|---|---|---|
| ``open`` | ``accepted`` | alguém aceita, nominalmente (fila que recebe não é pessoa que aceitou) |
| ``open``, ``accepted``, ``reopened`` | ``fulfilled`` | com evidência |
| ``open``, ``accepted``, ``reopened`` | ``broken`` | o prazo escalado venceu de novo |
| ``fulfilled``, ``broken``, ``expired`` | ``reopened`` | a mesma necessidade volta |

Três regras que não dependem de ninguém lembrar:

- **sem dono possível, não se promete** (N04): ``make_commitment`` recusa dono
  vazio, e "encaminhei" sem destinatário nunca chega a ser dito;
- **prazo ausente vem com motivo e contingência**: fora do expediente, ou sem
  saber o expediente, o prazo é ``DeadlineAbsent`` e nada afirma um prazo que
  ninguém definiu;
- **prazo vencido é evento** (K22): ``due`` devolve cada prazo vencido uma vez só,
  e quem escala é o perfil (linha ``commitment.escalation``).

Cada mudança é um registro ``Commitment`` novo (o anterior fica como estava, N14).
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Literal

from conversational_commerce.contracts import Commitment, DeploymentProfile, Known
from conversational_commerce.contracts.commitment import DeadlineAbsent, DeadlineSet
from conversational_commerce.contracts.common import Fact

from ..authority.grants import later

ESCALATION_LINE = "commitment.escalation"
OPEN_STATES = ("open", "accepted", "reopened")
TRANSITIONS: dict[str, frozenset[str]] = {
    "open": frozenset({"accepted", "fulfilled", "broken", "expired"}),
    "accepted": frozenset({"fulfilled", "broken", "expired"}),
    "reopened": frozenset({"accepted", "fulfilled", "broken", "expired"}),
    "fulfilled": frozenset({"reopened"}),
    "broken": frozenset({"reopened"}),
    "expired": frozenset({"reopened"}),
}

Window = Literal["respond", "accept"]
EventKind = Literal["acknowledged", "accepted", "fulfilled", "deadline_passed", "escalated", "escalation_absent",
                    "broken", "contingency", "customer_notified", "customer_notify_failed", "customer_notify_gave_up"]


class CommitmentRefused(Exception):
    """O compromisso não pode ser feito (sem dono possível, transição inválida)."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code


def staff_owner(profile: DeploymentProfile, operation: str) -> str | None:
    """O dono possível na equipe: a fila do perfil, se o adaptador da equipe faz a operação."""
    queue = profile.staff_queue
    if queue is None or operation not in profile.adapters.get("staff", ()):
        return None
    return queue.role


def window_seconds(profile: DeploymentProfile, window: Window) -> int:
    queue = profile.staff_queue
    return queue.accept_within_seconds if window == "accept" else queue.respond_within_seconds


def staff_deadline(profile: DeploymentProfile, hours: Fact | None, now: str, window: Window):
    """O prazo da equipe, ou a falta dele com motivo e a contingência do perfil.

    Fora do expediente (ou sem saber o expediente) ninguém da equipe responde no
    prazo da fila: não se afirma esse prazo.
    """
    queue = profile.staff_queue
    if not isinstance(hours, Known) or not isinstance(hours.value, Mapping) or "open" not in hours.value:
        return DeadlineAbsent(absent_reason="business_hours_unknown", contingency=queue.after_hours_contingency)
    if hours.value["open"] is not True:
        return DeadlineAbsent(absent_reason="outside_business_hours", contingency=queue.after_hours_contingency)
    return DeadlineSet(at=later(now, window_seconds(profile, window)), rule_ref=f"staff_queue.{window}_within_seconds")


def make_commitment(*, record: Mapping[str, Any], commitment_id: str, type: Literal["promise", "case"],
                    obligation: str, owner: str | None, deadline, criterion: str, problem_code: str | None = None,
                    requested_resolution: str | None = None) -> Commitment:
    """O compromisso novo, ``open``. Sem dono possível, recusa: a promessa não é feita (N04)."""
    if not owner:
        raise CommitmentRefused("no_owner_possible", "sem dono possível, não se promete")
    return Commitment(**record, commitment_id=commitment_id, type=type, obligation=obligation, owner=owner,
                      deadline=deadline, fulfillment_criterion=criterion, state="open", problem_code=problem_code,
                      requested_resolution=requested_resolution)


@dataclass(frozen=True, slots=True)
class CommitmentEvent:
    kind: EventKind
    commitment_id: str
    at: str
    ref: str | None = None


@dataclass
class Entry:
    """Um compromisso no livro: o registro vigente, o histórico e o que é preciso para retomá-lo."""

    commitment: Commitment
    move: str
    need: Any
    binding: Any
    recipient: str
    identity: str = "anonymous"
    ticket_id: str | None = None
    history: list[Commitment] = field(default_factory=list)
    notified: bool = False
    escalated: bool = False

    @property
    def commitment_id(self) -> str:
        return self.commitment.commitment_id

    @property
    def is_open(self) -> bool:
        return self.commitment.state in OPEN_STATES


@dataclass
class CommitmentLedger:
    entries: dict[str, Entry] = field(default_factory=dict)
    events: list[CommitmentEvent] = field(default_factory=list)
    # (compromisso, prazo) já tratados: cada prazo vencido é evento uma vez só.
    _handled: set[tuple[str, str]] = field(default_factory=set)

    def open(self, commitment: Commitment, **entry: Any) -> Entry:
        if commitment.commitment_id in self.entries:
            raise CommitmentRefused("duplicate_commitment", commitment.commitment_id)
        if commitment.state != "open":
            raise CommitmentRefused("not_open", "o compromisso nasce aberto")
        opened = Entry(commitment, history=[commitment], **entry)
        self.entries[commitment.commitment_id] = opened
        self.note("acknowledged", commitment.commitment_id, commitment.occurred_at, commitment.owner)
        return opened

    def advance(self, commitment_id: str, *, record_id: str, at: str, cause_id: str, **changes: Any) -> Commitment:
        """O registro seguinte do compromisso: mesma identidade, transição conferida, evidência só cresce."""
        entry = self.entries[commitment_id]
        current = entry.commitment
        target = changes.get("state", current.state)
        if target != current.state and target not in TRANSITIONS[current.state]:
            raise CommitmentRefused("invalid_transition", f"{current.state} → {target}")
        evidence = changes.pop("evidence", ())
        if target == "reopened":
            changes["reopened_from"] = current.id
        updated = dataclasses.replace(current, id=record_id, occurred_at=at, cause_id=cause_id, recorded_at=None,
                                      evidence=(*current.evidence, *evidence), **changes)
        entry.commitment = updated
        entry.history.append(updated)
        if target != current.state and target in ("accepted", "fulfilled", "broken"):
            self.note(target, commitment_id, at, evidence[0] if evidence else changes.get("owner"))
        return updated

    def note(self, kind: EventKind, commitment_id: str, at: str, ref: str | None = None) -> None:
        self.events.append(CommitmentEvent(kind, commitment_id, at, ref))

    def events_of(self, commitment_id: str) -> list[str]:
        return [event.kind for event in self.events if event.commitment_id == commitment_id]

    def latest(self, commitment_id: str) -> Commitment:
        return self.entries[commitment_id].commitment

    def open_entries(self, tenant: str | None = None, environment: str | None = None) -> list[Entry]:
        return [entry for entry in self.entries.values() if entry.is_open
                and (tenant is None or entry.commitment.tenant == tenant)
                and (environment is None or entry.commitment.environment == environment)]

    def open_episodes(self, tenant: str | None = None) -> frozenset[str]:
        return frozenset(entry.commitment.episode_id for entry in self.open_entries(tenant))

    def due(self, now: str, tenant: str | None = None, environment: str | None = None) -> list[Entry]:
        """Compromissos abertos com prazo vencido e ainda não tratado. Cada prazo, uma vez."""
        found = []
        for entry in self.open_entries(tenant, environment):
            deadline = entry.commitment.deadline
            if not isinstance(deadline, DeadlineSet) or deadline.at > now:
                continue
            key = (entry.commitment_id, deadline.at)
            if key in self._handled:
                continue
            self._handled.add(key)
            found.append(entry)
        return found
