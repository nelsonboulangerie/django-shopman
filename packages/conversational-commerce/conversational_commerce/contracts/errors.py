"""Erros estáveis do pacote e o erro de contrato.

``ErrorCode`` é o enum único de erros estáveis (v2 5.4). Mora aqui, e não no
catálogo, porque é tipo de valor de contrato: o ``ActionReceipt`` carrega um
``error.code`` desse enum. O significado operacional de cada código (quem o
devolve, o que fazer depois) é do ``spec/02-catalog-profile.md`` (F2).

``ContractError`` é o que a validação de contrato levanta. Usa só dois códigos:
``unsupported_schema`` (contrato ou versão que este leitor não conhece) e
``invalid_content`` (todo o resto: campo faltando, tipo errado, campo
desconhecido, número de ponto flutuante, hash que não confere, combinação
proibida). Erro não classificado nunca vira sucesso: quem chama trata
``ContractError`` como recusa.
"""

from __future__ import annotations

from enum import StrEnum


class ErrorCode(StrEnum):
    UNSUPPORTED_SCHEMA = "unsupported_schema"
    INVALID_CONTENT = "invalid_content"
    CAPABILITY_MISSING = "capability_missing"
    IDENTITY_INSUFFICIENT = "identity_insufficient"
    OBJECT_FORBIDDEN = "object_forbidden"
    FACT_UNAVAILABLE = "fact_unavailable"
    TERMS_CHANGED = "terms_changed"
    REVISION_CONFLICT = "revision_conflict"
    AUTHORITY_REVOKED = "authority_revoked"
    GRANT_EXPIRED = "grant_expired"
    CONFIRMATION_REQUIRED = "confirmation_required"
    IDEMPOTENCY_CONFLICT = "idempotency_conflict"
    EFFECT_PENDING = "effect_pending"
    EFFECT_UNKNOWN = "effect_unknown"
    BUDGET_EXHAUSTED = "budget_exhausted"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    # Recebimento (``set_fulfillment``) bem formado que a casa não atende. Forma inválida é ``invalid_content``.
    FULFILLMENT_UNAVAILABLE = "fulfillment_unavailable"


class ContractError(ValueError):
    """Um documento ou registro não cumpre o contrato.

    ``code`` é ``unsupported_schema`` ou ``invalid_content``; ``path`` aponta o
    campo (``"items.0.unit_price.currency"``), vazio quando o problema é do
    documento inteiro.
    """

    def __init__(self, code: ErrorCode, message: str, path: tuple[str | int, ...] = ()):
        self.code = ErrorCode(code)
        self.message = message
        self.path = tuple(path)
        super().__init__(self._render())

    @property
    def dotted_path(self) -> str:
        return ".".join(str(part) for part in self.path)

    def _render(self) -> str:
        where = self.dotted_path
        return f"{self.code.value}: {where}: {self.message}" if where else f"{self.code.value}: {self.message}"

    def prefixed(self, *segments: str | int) -> ContractError:
        """O mesmo erro, com ``segments`` antes do caminho atual."""
        return ContractError(self.code, self.message, (*segments, *self.path))


def invalid(message: str, *path: str | int) -> ContractError:
    return ContractError(ErrorCode.INVALID_CONTENT, message, path)


def unsupported(message: str, *path: str | int) -> ContractError:
    return ContractError(ErrorCode.UNSUPPORTED_SCHEMA, message, path)
