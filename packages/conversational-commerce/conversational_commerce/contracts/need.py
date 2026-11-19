"""``Need``: um item da agenda dentro do episódio (observação, v2 5.7).

*Satisfeita* exige evidência; *retirada* exige ato do cliente ou regra do
perfil, nunca silêncio; bloqueada segura as que dependem dela.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .common import CONTRACT_DATACLASS, Identifier, ObservationRecord
from .errors import invalid
from .validate import require_unique

NeedState = Literal["open", "blocked", "satisfied", "withdrawn"]


@dataclass(**CONTRACT_DATACLASS)
class Need(ObservationRecord):
    SCHEMA = "cc.need"
    KIND = "Need"

    need_id: Identifier
    type: Identifier
    state: NeedState
    depends_on: tuple[Identifier, ...] = ()
    evidence: tuple[Identifier, ...] = ()

    def check(self) -> None:
        if self.episode_id is None:
            raise invalid("necessidade pertence a um episódio", "episode_id")
        if self.need_id in self.depends_on:
            raise invalid("necessidade não depende de si mesma", "depends_on")
        require_unique(self.depends_on, "depends_on")
        if self.state in ("satisfied", "withdrawn") and not self.evidence:
            raise invalid(f"necessidade {self.state} exige evidência", "evidence")
