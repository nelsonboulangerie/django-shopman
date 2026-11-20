"""Sondas do Watchman da superfície de cliente (o kernel ``shopman.watchman`` não importa o host)."""

from __future__ import annotations

from shopman.watchman.contracts import CheckContext, CheckResult, Scope, Status


class ConciergeReadingCheck:
    """A Concierge atende com modelo na leitura de partes (dono, 19/11/2026).

    Falha com a Concierge ligada e a leitura sem modelo, com a causa (sem conexão, sem
    chave, freio de gasto, provedor falhando). Desligada, pula. Não chama modelo.
    """

    id = "concierge_reading"
    description = "The WhatsApp Concierge reads customer messages with a model."
    scopes = frozenset({Scope.DIAGNOSTIC})
    timeout_seconds = 2.0

    def run(self, context: CheckContext) -> CheckResult:
        from shopman.storefront.concierge import reading_health

        state = reading_health.current()
        if not state.active:
            return CheckResult(id=self.id, status=Status.SKIPPED, summary="the Concierge is not answering")
        if not state.without_model:
            return CheckResult(id=self.id, status=Status.PASS, summary="the Concierge reads with a model")
        return CheckResult(
            id=self.id,
            status=Status.FAIL,
            summary=f"the Concierge is answering without a model ({state.cause})",
            evidence={"cause": state.cause},
            remediation="Configure the AI connection of the 'intents' route (Admin, AI connections) or lift the spend brake.",
        )
