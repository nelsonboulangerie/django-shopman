"""Porta de resultados: colher uma métrica de um episódio ou cliente numa janela.

Garantias (v2 5.4, N20, N21): fonte independente do agente; resultado imaturo
é ``censored``, não fracasso; correção chega como registro que ``supersedes``;
desconhecido explícito, nunca zero.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from conversational_commerce.contracts import MetricRef, OutcomeEvent, Window

from .common import Capabilities, TrustedContext

OPERATIONS = ("harvest",)


@runtime_checkable
class OutcomesPort(Protocol):
    def capabilities(self) -> Capabilities: ...

    def harvest(self, ctx: TrustedContext, metric: MetricRef, subject: str, window: Window) -> OutcomeEvent: ...
