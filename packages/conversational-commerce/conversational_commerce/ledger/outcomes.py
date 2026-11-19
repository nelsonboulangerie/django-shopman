"""O livro dos resultados: só acrescenta, com censura e supersessão (v2 5.5, 8.5; N14, N20, N21).

- **Fonte independente**: o resultado vem da porta de resultados, nunca de quem
  decidiu (N20). O livro recusa resultado cuja fonte é o próprio núcleo.
- **Janela aberta é censura**, não zero nem fracasso (K33): resultado colhido
  antes do fim da janela é ``censored`` e não entra em taxa nenhuma.
- **Desconhecido não vira zero** (N21): ``unknown`` fica fora das contas e é contado
  à parte.
- **Correção substitui, e o histórico fica** (K35): o registro que ``supersedes``
  outro passa a valer; o anterior continua no livro e sai das contas.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from conversational_commerce.contracts import MetricRef, OutcomeEvent, Window
from conversational_commerce.ports import TrustedContext

from .decisions import LedgerError

# Fontes que são o próprio agente: quem aprende não escreve o resultado pelo qual é avaliado (N20).
SELF_SOURCES = frozenset({"conversational-commerce", "engine", "core"})


@dataclass
class OutcomeLedger:
    history: list[OutcomeEvent] = field(default_factory=list)

    def record(self, outcome: OutcomeEvent) -> OutcomeEvent:
        if outcome.source in SELF_SOURCES:
            raise LedgerError("self_reported_outcome", "o resultado vem de fonte independente do agente (N20)")
        if any(existing.id == outcome.id for existing in self.history):
            raise LedgerError("duplicate_outcome", outcome.id)
        if outcome.supersedes is not None:
            if outcome.supersedes not in {existing.id for existing in self.history}:
                raise LedgerError("unknown_supersedes", outcome.supersedes)
            if outcome.supersedes in self._superseded():
                raise LedgerError("already_superseded", outcome.supersedes)
        self.history.append(outcome)
        return outcome

    def harvest(self, ctx: TrustedContext, port, metric: MetricRef, subject: str, window: Window) -> OutcomeEvent:
        """Colhe pela porta e grava. Janela aberta vem ``censored`` da porta, e o livro confere de novo."""
        outcome = port.harvest(ctx, metric, subject, window)
        if outcome.observation == "observed" and window.end > outcome.occurred_at:
            raise LedgerError("immature_observed", "janela aberta não tem resultado observado: é censura (K33)")
        return self.record(outcome)

    def _superseded(self) -> set[str]:
        return {item.supersedes for item in self.history if item.supersedes is not None}

    def current(self, metric_id: str | None = None, subject: str | None = None) -> tuple[OutcomeEvent, ...]:
        """O que vale: nada substituído."""
        gone = self._superseded()
        return tuple(item for item in self.history if item.id not in gone
                     and (metric_id is None or item.metric.id == metric_id)
                     and (subject is None or item.customer_ref == subject))

    def chain(self, outcome_id: str) -> tuple[OutcomeEvent, ...]:
        """O histórico de um resultado: do primeiro ao que vale, cada correção na ordem."""
        by_id = {item.id: item for item in self.history}
        replaced_by = {item.supersedes: item for item in self.history if item.supersedes is not None}
        start = by_id[outcome_id]
        while start.supersedes is not None:
            start = by_id[start.supersedes]
        chain = [start]
        while chain[-1].id in replaced_by:
            chain.append(replaced_by[chain[-1].id])
        return tuple(chain)


@dataclass(frozen=True, slots=True)
class OutcomeSummary:
    """A leitura de um conjunto de resultados, sem transformar o que falta em número.

    ``mean`` é ``None`` quando nada foi observado: desconhecido e censurado não viram zero.
    """

    observed: int
    censored: int
    unknown: int
    not_applicable: int
    mean: str | None


def summarize(outcomes: Iterable[OutcomeEvent]) -> OutcomeSummary:
    from decimal import Decimal

    counts = {"observed": 0, "censored": 0, "unknown": 0, "not_applicable": 0}
    values = []
    for outcome in outcomes:
        counts[outcome.observation] += 1
        if outcome.observation == "observed":
            values.append(Decimal(str(outcome.value)))
    mean = None if not values else str(sum(values) / len(values))
    return OutcomeSummary(**counts, mean=mean)
