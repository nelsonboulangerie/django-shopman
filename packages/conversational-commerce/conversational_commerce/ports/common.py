"""O que toda porta compartilha: contexto confiável, capacidades e erro tipado.

Toda chamada recebe o ``TrustedContext`` (inquilino, ambiente, sujeito), que
nunca nasce de texto do cliente (v2 5.4). Toda porta responde
``capabilities()``: o que faz, com que garantias, e o que NÃO faz. Todo erro de
porta é ``PortError`` com um código do enum estável; erro não classificado
nunca vira sucesso, e se a submissão PODE ter ocorrido o código é
``effect_unknown``.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Literal

from conversational_commerce.contracts.canonical import FrozenMap
from conversational_commerce.contracts.common import (
    CONTRACT_DATACLASS,
    Environment,
    Identifier,
    JsonValue,
    Value,
)
from conversational_commerce.contracts.errors import ErrorCode

PortName = Literal["channel", "model", "commerce_read", "commerce_execute", "staff", "store", "clock", "outcomes"]

PORT_NAMES: tuple[str, ...] = (
    "channel",
    "model",
    "commerce_read",
    "commerce_execute",
    "staff",
    "store",
    "clock",
    "outcomes",
)


@dataclass(**CONTRACT_DATACLASS)
class TrustedContext(Value):
    """Quem pede, em que inquilino e ambiente. Montado pelo núcleo, nunca pelo texto."""

    tenant: Identifier
    environment: Environment
    subject: Identifier | None = None


@dataclass(**CONTRACT_DATACLASS)
class Capabilities(Value):
    """O que a porta declara: operações, garantias e o que não suporta.

    ``guarantees`` é livre por porta (``idempotency_retention_seconds``,
    ``read_receipts``, ``atomic_effect_guard``...); a lista de chaves que cada
    porta deve declarar está em ``spec/03-ports.md``.
    """

    port: PortName
    operations: tuple[Identifier, ...]
    guarantees: Mapping[str, JsonValue] = field(default_factory=FrozenMap)
    unsupported: tuple[Identifier, ...] = ()

    def supports(self, operation: str) -> bool:
        return operation in self.operations and operation not in self.unsupported


class PortError(Exception):
    """Erro tipado de porta. ``code`` é do enum estável (``ErrorCode``)."""

    def __init__(self, code: ErrorCode | str, message: str = ""):
        self.code = ErrorCode(code)
        self.message = message
        super().__init__(f"{self.code.value}: {message}" if message else self.code.value)

    @property
    def may_have_happened(self) -> bool:
        """Se a submissão pode ter ocorrido: então é reconciliação, nunca falha sem efeito."""
        return self.code in (ErrorCode.EFFECT_UNKNOWN, ErrorCode.EFFECT_PENDING)
