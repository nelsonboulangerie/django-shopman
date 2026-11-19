"""``Episode``: a unidade de trabalho e de medida (observação, v2 5.7).

Encerrar a conversa não resolve o episódio. A época de posse só cresce; todo
comando carrega a época esperada.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .common import CONTRACT_DATACLASS, Identifier, Instant, NonNegativeInt, ObservationRecord, Text, Value
from .errors import invalid
from .validate import require_order, require_unique

EpisodeState = Literal[
    "active",
    "waiting_input",
    "waiting_authorization",
    "waiting_effect",
    "awaiting_handoff",
    "human_owned",
    "resolved",
]


@dataclass(**CONTRACT_DATACLASS)
class Ownership(Value):
    owner: Literal["automation", "queue", "person"]
    epoch: NonNegativeInt
    # Quem, quando a posse é de uma fila ou pessoa.
    holder_ref: Identifier | None = None

    def check(self) -> None:
        if self.owner == "automation" and self.holder_ref is not None:
            raise invalid("posse da automação não tem holder_ref", "holder_ref")


@dataclass(**CONTRACT_DATACLASS)
class Wait(Value):
    """Toda espera tem condição de retomada, responsável e prazo."""

    condition: Text
    owner: Identifier
    deadline: Instant


@dataclass(**CONTRACT_DATACLASS)
class Episode(ObservationRecord):
    SCHEMA = "cc.episode"
    KIND = "Episode"

    subject: Identifier | None = None
    state: EpisodeState
    version: NonNegativeInt
    ownership: Ownership
    needs: tuple[Identifier, ...] = ()
    waits: tuple[Wait, ...] = ()
    opened_at: Instant
    resolved_at: Instant | None = None
    reopened_from: Identifier | None = None

    def check(self) -> None:
        if self.episode_id is None:
            raise invalid("o registro de episódio carrega o próprio episode_id", "episode_id")
        require_unique(self.needs, "needs")
        require_order(self.opened_at, self.resolved_at, "resolved_at")
        if (self.state == "resolved") != (self.resolved_at is not None):
            raise invalid("resolved_at existe se, e só se, o estado é resolved", "resolved_at")
        if self.state == "human_owned" and self.ownership.owner != "person":
            raise invalid("human_owned exige posse de pessoa", "ownership")
