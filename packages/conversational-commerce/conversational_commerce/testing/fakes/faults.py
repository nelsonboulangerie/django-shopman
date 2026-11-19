"""Falhas injetáveis dos adaptadores falsos.

Cada falso consulta o seu ``FaultPlan`` a cada operação: ``plan.take(op)``
devolve a próxima falha armada para aquela operação, ou ``None``. Uma falha
armada vale um número de vezes (``times``) e depois some, para que o teste diga
exatamente onde o mundo quebra.
"""

from __future__ import annotations

from collections import defaultdict, deque
from enum import StrEnum


class Fault(StrEnum):
    # Canal.
    DUPLICATE_DELIVERY = "duplicate_delivery"
    OUT_OF_ORDER = "out_of_order"
    SEND_UNKNOWN = "send_unknown"
    # Modelo.
    OUT_OF_SCHEMA = "out_of_schema"
    ACT_OUTSIDE_LIST = "act_outside_list"
    BUDGET_EXHAUSTED = "budget_exhausted"
    # Qualquer porta que fala com um provedor.
    PROVIDER_DOWN = "provider_down"
    # Comércio, leitura.
    SOURCE_FAILED = "source_failed"
    STALE_FACT = "stale_fact"
    PRICE_CHANGES_AFTER_QUOTE = "price_changes_after_quote"
    # Comércio, execução.
    CRASH_BEFORE_EFFECT = "crash_before_effect"
    CRASH_AFTER_EFFECT = "crash_after_effect"
    EFFECT_PENDING = "effect_pending"
    # Equipe.
    QUEUE_REJECTS = "queue_rejects"
    LATE_ANSWER = "late_answer"
    # Armazenamento.
    VERSION_CONFLICT = "version_conflict"
    WORKER_DIES = "worker_dies"
    DOUBLE_CLAIM = "double_claim"
    # Resultados.
    IMMATURE = "immature"
    CORRECTED_LATER = "corrected_later"


class FaultPlan:
    """Falhas armadas por operação, em ordem."""

    def __init__(self) -> None:
        self._armed: dict[str, deque[Fault]] = defaultdict(deque)
        self.fired: list[tuple[str, Fault]] = []

    def arm(self, operation: str, fault: Fault, times: int = 1) -> FaultPlan:
        for _ in range(times):
            self._armed[operation].append(Fault(fault))
        return self

    def take(self, operation: str) -> Fault | None:
        queue = self._armed.get(operation)
        if not queue:
            return None
        fault = queue.popleft()
        self.fired.append((operation, fault))
        return fault

    def pending(self) -> dict[str, list[Fault]]:
        return {op: list(queue) for op, queue in self._armed.items() if queue}
