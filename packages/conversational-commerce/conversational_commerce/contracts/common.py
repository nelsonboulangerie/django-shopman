"""Envelope comum, tipos de valor e as bases de todo contrato.

Cada contrato é uma ``dataclass(frozen=True, slots=True, kw_only=True)``. A
validação mora no próprio construtor (``__post_init__``): um registro que
existe em memória já cumpre o contrato, e não há como montar um inválido. A
anotação de tipo de cada campo É o contrato; ``validate.py`` a lê, e
``schema_export.py`` gera o JSON Schema a partir dela.

Três bases:

- ``Value``: objeto aninhado (dinheiro, quantidade, fato...). Sempre estrito.
- ``StrictRecord``: contrato de execução e autorização. Recusa campo
  desconhecido e qualquer versão fora de ``SUPPORTED_VERSIONS``.
- ``ObservationRecord``: contrato de observação. Aceita MENOR acima do seu e
  guarda o campo desconhecido em ``extensions``, sem interpretar; MAIOR
  diferente é recusa.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Annotated, Any, ClassVar, Literal

from .canonical import FrozenMap


class Rule(StrEnum):
    """Restrições de valor que a anotação carrega (``Annotated[tipo, Rule.X]``)."""

    IDENTIFIER = "identifier"
    TEXT = "text"
    INSTANT = "instant"
    CURRENCY = "currency"
    DECIMAL = "decimal"
    HASH = "hash"
    VERSION = "version"
    NON_NEGATIVE = "non_negative"
    POSITIVE = "positive"
    JSON = "json"
    JSON_OBJECT = "json_object"


# Texto não vazio, sem espaço nas pontas: identificador opaco.
Identifier = Annotated[str, Rule.IDENTIFIER]
# Texto livre não vazio (referência, motivo, descrição curta).
Text = Annotated[str, Rule.TEXT]
# Instante em UTC, sempre com microssegundos: 2026-11-18T14:03:00.000000Z.
Instant = Annotated[str, Rule.INSTANT]
# Código ISO 4217 de três letras maiúsculas.
CurrencyCode = Annotated[str, Rule.CURRENCY]
# Decimal em texto, forma normalizada: sem zero à esquerda nem à direita, sem "-0".
DecimalText = Annotated[str, Rule.DECIMAL]
# sha256:<64 hex minúsculos>.
Hash = Annotated[str, Rule.HASH]
# Versão de esquema MAIOR.MENOR.
SchemaVersion = Annotated[str, Rule.VERSION]
NonNegativeInt = Annotated[int, Rule.NON_NEGATIVE]
PositiveInt = Annotated[int, Rule.POSITIVE]
# Qualquer valor JSON, congelado; sem float.
JsonValue = Annotated[Any, Rule.JSON]
# Objeto JSON, congelado; sem float.
JsonObject = Annotated[FrozenMap, Rule.JSON_OBJECT]

Environment = Literal["test", "shadow", "live"]
IdentityAssurance = Literal["anonymous", "transported", "weak_verified", "strong_verified"]
EventAssurance = Literal["verified", "provider_claimed", "none"]
AuthorityLevel = Literal["A0", "A1", "A2", "A3", "A4", "A5"]
UnknownReason = Literal["source_failed", "stale", "not_supported", "forbidden", "not_found"]

IDENTITY_LADDER: tuple[str, ...] = ("anonymous", "transported", "weak_verified", "strong_verified")
AUTHORITY_LEVELS: tuple[str, ...] = ("A0", "A1", "A2", "A3", "A4", "A5")

CONTRACT_DATACLASS = {"frozen": True, "slots": True, "kw_only": True}


def _post_init(self) -> None:
    from .validate import check_instance

    check_instance(self)


@dataclass(**CONTRACT_DATACLASS)
class Value:
    """Objeto aninhado de contrato. Estrito: campo desconhecido é recusa."""

    def __post_init__(self) -> None:
        _post_init(self)

    def check(self) -> None:
        """Regras que cruzam campos. Levanta ``ContractError``."""


@dataclass(**CONTRACT_DATACLASS)
class Producer(Value):
    name: Identifier
    version: Text


@dataclass(**CONTRACT_DATACLASS)
class VersionRef(Value):
    id: Identifier
    version: Text


@dataclass(**CONTRACT_DATACLASS)
class Money(Value):
    """Dinheiro: inteiro na menor unidade da moeda. Nunca float."""

    amount_minor: int
    currency: CurrencyCode


@dataclass(**CONTRACT_DATACLASS)
class Quantity(Value):
    """Quantidade: decimal em texto normalizado, com unidade. Nunca float."""

    value: DecimalText
    unit: Identifier


@dataclass(**CONTRACT_DATACLASS)
class Known(Value):
    """Fato conhecido: valor com fonte, instante da observação e validade."""

    status: Literal["known"] = "known"
    value: JsonValue
    source: Identifier
    observed_at: Instant
    valid_until: Instant | None = None
    source_version: Text | None = None

    def check(self) -> None:
        from .validate import require_order

        require_order(self.observed_at, self.valid_until, "valid_until", strict=True)


@dataclass(**CONTRACT_DATACLASS)
class Unknown(Value):
    """Fato desconhecido. Vencido é ``Unknown(stale)``, nunca o valor velho."""

    status: Literal["unknown"] = "unknown"
    reason: UnknownReason


Fact = Known | Unknown


@dataclass(**CONTRACT_DATACLASS)
class Estimate(Value):
    """Estimativa com método, população e versão. ``value`` é decimal em texto."""

    status: Literal["estimate"] = "estimate"
    value: DecimalText
    method: Identifier
    population: Identifier
    version: Text


@dataclass(**CONTRACT_DATACLASS)
class Unavailable(Value):
    """Sem estimativa. Nunca zero no lugar de desconhecido (N21)."""

    status: Literal["unavailable"] = "unavailable"
    reason: Identifier


Prediction = Estimate | Unavailable


@dataclass(**CONTRACT_DATACLASS)
class IdentityEvidence(Value):
    """Evidência de identidade: de onde vem e que degrau da escada ela sustenta."""

    kind: Identifier
    ref: Identifier
    assurance: IdentityAssurance


@dataclass(**CONTRACT_DATACLASS)
class Record:
    """Envelope comum de todo contrato.

    ``schema`` e ``kind`` são constantes da classe e saem no documento;
    ``schema_version`` vazio no construtor vira a versão corrente do contrato.
    ``recorded_at`` só a fronteira de persistência preenche, e fica fora do hash.
    """

    SCHEMA: ClassVar[str] = ""
    KIND: ClassVar[str] = ""
    VERSION: ClassVar[str] = "1.0"
    STRICT: ClassVar[bool] = True
    # Campo que guarda o hash do próprio documento, quando o contrato tem um.
    HASH_FIELD: ClassVar[str | None] = None

    id: Identifier
    tenant: Identifier
    environment: Environment
    trace_id: Identifier
    cause_id: Identifier | None = None
    occurred_at: Instant
    recorded_at: Instant | None = None
    producer: Producer
    episode_id: Identifier | None = None
    schema_version: SchemaVersion = ""

    def __post_init__(self) -> None:
        _post_init(self)

    def check(self) -> None:
        """Regras que cruzam campos. Levanta ``ContractError``."""

    @classmethod
    def from_document(cls, document: Mapping[str, Any]):
        """Lê um documento JSON (já decodificado) e devolve o registro validado."""
        from .validate import parse_record

        return parse_record(cls, document)

    def to_document(self) -> dict[str, Any]:
        """O documento JSON do registro, pronto para a forma canônica."""
        from .errors import invalid
        from .validate import encode_record

        hash_field = type(self).HASH_FIELD
        if hash_field is not None and getattr(self, hash_field) is None:
            raise invalid("rascunho sem hash não vira documento; use seal()", hash_field)
        return encode_record(self)


@dataclass(**CONTRACT_DATACLASS)
class StrictRecord(Record):
    """Contrato de execução ou autorização: estrito em campo e em versão."""

    SUPPORTED_VERSIONS: ClassVar[frozenset[str]] = frozenset({"1.0"})


@dataclass(**CONTRACT_DATACLASS)
class ObservationRecord(Record):
    """Contrato de observação: leitor tolerante a MENOR acima."""

    STRICT: ClassVar[bool] = False

    extensions: JsonObject = field(default_factory=FrozenMap)
