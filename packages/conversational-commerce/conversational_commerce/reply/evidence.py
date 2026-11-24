"""A evidência que lastreia uma resposta: fatos, recibos, compromissos, linhas de política e leituras.

Toda afirmação aponta uma chave daqui. O que não está aqui não pode ser dito,
e o que está aqui mas não vale (fato ``Unknown`` ou vencido, recibo que não é
sucesso) também não sustenta a afirmação.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from conversational_commerce.contracts import ActionReceipt, Commitment, Known, Unknown
from conversational_commerce.contracts.common import Fact


@dataclass(frozen=True, slots=True)
class Evidence:
    now: str
    facts: Mapping[str, Fact] = field(default_factory=dict)
    # Faceta de cada fato, quando importa o tipo da leitura (``factual``, ``promisable``...).
    fact_facets: Mapping[str, str] = field(default_factory=dict)
    receipts: Mapping[str, ActionReceipt] = field(default_factory=dict)
    commitments: Mapping[str, Commitment] = field(default_factory=dict)
    policies: Mapping[str, Any] = field(default_factory=dict)
    # As leituras que o agente repete para confirmar (ADR-051): o que o CLIENTE disse, nunca afirmação da casa.
    readings: Mapping[str, Any] = field(default_factory=dict)

    def kinds_of(self, backing: str, ref: str) -> tuple[str, ...]:
        """Os tipos de lastro que ``ref`` oferece, para casar com o que o espaço do molde aceita."""
        if backing == "fact" and ref in self.facts:
            facet = self.fact_facets.get(ref)
            return ("fact", f"fact:{facet}") if facet else ("fact",)
        if backing == "receipt" and ref in self.receipts:
            return ("receipt", f"receipt:{self.receipts[ref].status}")
        if backing == "commitment" and ref in self.commitments:
            return ("commitment", f"commitment:{self.commitments[ref].type}")
        if backing == "policy" and ref in self.policies:
            return ("policy",)
        if backing == "reading" and ref in self.readings:
            return ("reading",)
        return ()

    def problem(self, backing: str, ref: str | None) -> str | None:
        """Por que o lastro não sustenta uma afirmação; ``None`` quando sustenta."""
        if backing == "courtesy":
            return None
        if ref is None:
            return "claim_without_backing"
        if backing == "fact":
            fact = self.facts.get(ref)
            if fact is None:
                return "fact_not_in_evidence"
            if isinstance(fact, Unknown):
                return "fact_unknown"
            if isinstance(fact, Known) and fact.valid_until is not None and fact.valid_until <= self.now:
                return "fact_expired"
            return None
        if backing == "receipt":
            return None if ref in self.receipts else "receipt_not_in_evidence"
        if backing == "commitment":
            return None if ref in self.commitments else "commitment_not_in_evidence"
        if backing == "policy":
            return None if ref in self.policies else "policy_not_in_evidence"
        if backing == "reading":
            return None if ref in self.readings else "reading_not_in_evidence"
        return "unknown_backing"

    def value(self, backing: str, ref: str, field_name: str | None) -> Any:
        """O valor que preenche o espaço, lido só da evidência."""
        if backing == "fact":
            value = self.facts[ref].value  # type: ignore[union-attr]
        elif backing == "receipt":
            receipt = self.receipts[ref]
            value = dict(receipt.domain_refs) if field_name else receipt.status
        elif backing == "commitment":
            commitment = self.commitments[ref]
            deadline = commitment.deadline
            value = {"at": getattr(deadline, "at", None), "owner": commitment.owner, "state": commitment.state}
        elif backing == "reading":
            value = self.readings[ref]
        else:
            value = self.policies[ref]
        if field_name is not None:
            if not isinstance(value, Mapping) or field_name not in value:
                raise KeyError(f"{backing}:{ref} não tem o campo {field_name!r}")
            value = value[field_name]
        return value
