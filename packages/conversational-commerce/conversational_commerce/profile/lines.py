"""Avaliação de linha do perfil.

Regra única (v2 5.8): campo sem decisão fica ``absent``, com motivo, e a ação
que depende dele fica inelegível, com código. Linha ``proposed`` ou
``validating`` não vale como aprovada: só ``approved`` com valor libera.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from conversational_commerce.contracts import DeploymentProfile, LineSet, ProfileLine

from .codes import IneligibilityCode


@dataclass(frozen=True, slots=True)
class LineReading:
    """O que uma linha diz: o valor, se vale; senão, o código de por que não vale."""

    line_id: str
    usable: bool
    value: Any = None
    code: IneligibilityCode | None = None
    state: str | None = None


def find_line(profile: DeploymentProfile, line_id: str) -> ProfileLine | None:
    for line in profile.lines:
        if line.id == line_id:
            return line
    return None


def read_line(profile: DeploymentProfile, line_id: str) -> LineReading:
    """Lê a linha ``line_id``. Só ``approved`` com valor é usável."""
    line = find_line(profile, line_id)
    if line is None:
        return LineReading(line_id, False, code=IneligibilityCode.PROFILE_LINE_ABSENT)
    if not isinstance(line.setting, LineSet):
        return LineReading(line_id, False, code=IneligibilityCode.PROFILE_LINE_ABSENT, state=line.state)
    if line.state != "approved":
        return LineReading(line_id, False, code=IneligibilityCode.PROFILE_LINE_NOT_APPROVED, state=line.state)
    return LineReading(line_id, True, value=line.setting.value, state=line.state)
