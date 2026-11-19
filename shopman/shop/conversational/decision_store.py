"""Gravar a decisão em sombra e o resultado dela, pelo contrato do framework (N5).

A forma de cada registro é a do framework: o ``DecisionRecord`` selado vira o documento da
decisão, e o resultado passa pelo ``OutcomeEvent`` (valor só quando observado, censura sem
valor) antes de virar linha. Aqui só se grava; quem decide é a sombra da Concierge.

- uma entrada, uma decisão (K01): gravar de novo a mesma mensagem devolve a que existe;
- o resultado novo substitui o vigente da mesma métrica (K35), e o anterior fica;
- resultado igual ao vigente não grava de novo: a junção pode rodar em todo ciclo.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

from conversational_commerce.contracts import DecisionRecord, OutcomeEvent, sha256_hash
from django.db import transaction

from shopman.shop.models import ConversationalDecision, ConversationalOutcome

FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"


def _moment(instant: str) -> datetime:
    return datetime.strptime(instant, FORMAT).replace(tzinfo=UTC)


def record_decision(*, message, conversation_id: int, decision: DecisionRecord, snapshot_hash: str,
                    acts: Sequence[str], unknown_facts: Mapping[str, str], customer_ref: str,
                    entry_at: datetime) -> tuple[ConversationalDecision, bool]:
    """A decisão da entrada. ``(registro, criado)``; a segunda gravação da mesma entrada não cria."""
    chosen = [decision.candidates[index].move for index in decision.chosen]
    blocked = {candidate.move: list(candidate.blocked_by) for candidate in decision.candidates
               if candidate.blocked_by}
    document = decision.to_document()
    with transaction.atomic():
        return ConversationalDecision.objects.get_or_create(
            message=message,
            defaults={
                "conversation_id": conversation_id, "environment": decision.environment,
                "decision_id": decision.decision_id, "decision_hash": sha256_hash(document),
                "snapshot_hash": snapshot_hash, "profile_version": str(decision.profile.version),
                "acts": list(acts), "chosen_moves": chosen, "blocked": blocked,
                "unknown_facts": dict(unknown_facts), "document": document,
                "customer_ref": customer_ref or "", "entry_at": entry_at,
                "decided_at": _moment(decision.occurred_at),
            },
        )


def current_outcome(decision: ConversationalDecision, metric: str) -> ConversationalOutcome | None:
    """O resultado que vale: o da métrica que ninguém substituiu."""
    return (ConversationalOutcome.objects.filter(decision=decision, metric=metric, superseded_by__isnull=True)
            .order_by("-recorded_at", "-pk").first())


def record_outcome(decision: ConversationalDecision, outcome: OutcomeEvent) -> ConversationalOutcome | None:
    """Grava o resultado, substituindo o vigente da métrica. ``None`` quando nada mudou."""
    metric = outcome.metric.id
    with transaction.atomic():
        ConversationalDecision.objects.select_for_update().filter(pk=decision.pk).first()
        current = current_outcome(decision, metric)
        if current is not None and current.observation == outcome.observation and current.value == _value(outcome):
            return None
        return ConversationalOutcome.objects.create(
            decision=decision, outcome_id=outcome.id, metric=metric,
            definition_version=outcome.metric.definition_version,
            window_start=_moment(outcome.window.start), window_end=_moment(outcome.window.end),
            observation=outcome.observation, value=_value(outcome), source=outcome.source, supersedes=current)


def _value(outcome: OutcomeEvent) -> Any:
    return outcome.value if outcome.observation == "observed" else None
