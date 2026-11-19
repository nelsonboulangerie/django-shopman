"""``ExposureEvent``: o que foi mostrado a quem, e até onde se sabe (observação).

Invariante (v2 5.5, N16): aceita não é lida; não poder medir leitura não é
"não leu"; envio desconhecido não se reenvia às cegas.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .common import CONTRACT_DATACLASS, Hash, Identifier, ObservationRecord, PositiveInt, Producer

ExposureState = Literal["prepared", "submitted", "accepted", "not_applied", "unknown", "delivered", "read"]


@dataclass(**CONTRACT_DATACLASS)
class ExposureEvent(ObservationRecord):
    SCHEMA = "cc.exposure_event"
    KIND = "ExposureEvent"

    decision_id: Identifier
    content_hash: Hash
    realizer: Producer
    recipient: Identifier
    attempt: PositiveInt
    state: ExposureState
