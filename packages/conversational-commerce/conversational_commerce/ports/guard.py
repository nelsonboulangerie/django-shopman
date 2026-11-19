"""A guarda do ponto de efeito: a autoridade não é porta (v2 5.4).

O núcleo emite a concessão e entrega ao executor uma ``EffectGuard``. O
executor TEM de chamar ``verify`` dentro da mesma unidade atômica do efeito
local, com o estado vigente naquele instante: o relógio, o hash dos termos
vigentes, as versões dos alvos e a época de posse. ``verify`` levanta
``PortError`` (``grant_expired``, ``authority_revoked``, ``terms_changed``,
``revision_conflict``) e o executor não aplica o efeito.

Aqui está só a forma. A guarda de verdade é do F8 (``spec/08-effect.md``).
Adaptador que não consegue chamar a guarda junto do efeito declara, em
``capabilities().guarantees``, ``atomic_effect_guard = false``, e a ação fica
indisponível para autonomia.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from conversational_commerce.contracts.canonical import FrozenMap
from conversational_commerce.contracts.common import CONTRACT_DATACLASS, Hash, Instant, NonNegativeInt, Value


@dataclass(**CONTRACT_DATACLASS)
class EffectState(Value):
    """O estado vigente no instante do efeito, como o executor o lê dentro da transação."""

    now: Instant
    terms_hash: Hash | None = None
    versions: Mapping[str, NonNegativeInt] = field(default_factory=FrozenMap)
    ownership_epoch: NonNegativeInt


@runtime_checkable
class EffectGuard(Protocol):
    def verify(self, state: EffectState) -> None:
        """Levanta ``PortError`` se o efeito não pode acontecer; não devolve nada se pode."""
        ...
