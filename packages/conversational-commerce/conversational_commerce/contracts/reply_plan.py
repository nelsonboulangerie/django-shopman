"""``ReplyPlan``: a resposta em partes, cada afirmação com lastro (observação).

Invariante (v2 5.5, N01): afirmação sem lastro não sai. Só cortesia dispensa
referência; fato, recibo, política e compromisso apontam o que sustenta.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .common import CONTRACT_DATACLASS, Identifier, NonNegativeInt, ObservationRecord, Value
from .errors import invalid

Backing = Literal["fact", "receipt", "policy", "commitment", "courtesy"]


@dataclass(**CONTRACT_DATACLASS)
class Claim(Value):
    slot: Identifier
    backing: Backing
    ref: Identifier | None = None

    def check(self) -> None:
        if self.backing == "courtesy" and self.ref is not None:
            raise invalid("cortesia não tem lastro a apontar", "ref")
        if self.backing != "courtesy" and self.ref is None:
            raise invalid(f"afirmação com lastro {self.backing} aponta o lastro", "ref")


@dataclass(**CONTRACT_DATACLASS)
class ReplyPart(Value):
    move: Identifier
    claims: tuple[Claim, ...] = ()


@dataclass(**CONTRACT_DATACLASS)
class Finding(Value):
    code: Identifier
    part: NonNegativeInt | None = None
    slot: Identifier | None = None


@dataclass(**CONTRACT_DATACLASS)
class Verification(Value):
    result: Literal["pass", "repair", "hold"]
    findings: tuple[Finding, ...] = ()

    def check(self) -> None:
        if self.result != "pass" and not self.findings:
            raise invalid(f"verificação {self.result} diz o que achou", "findings")


@dataclass(**CONTRACT_DATACLASS)
class ReplyPlan(ObservationRecord):
    SCHEMA = "cc.reply_plan"
    KIND = "ReplyPlan"

    decision_id: Identifier
    parts: tuple[ReplyPart, ...]
    locked_blocks: tuple[Identifier, ...] = ()
    verification: Verification

    def check(self) -> None:
        if not self.parts:
            raise invalid("plano de resposta sem parte", "parts")
        for index, finding in enumerate(self.verification.findings):
            if finding.part is not None and finding.part >= len(self.parts):
                raise invalid("achado aponta parte inexistente", "verification", "findings", index, "part")
