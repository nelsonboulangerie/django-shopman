"""Dublês adversariais do Marketing; nunca importados pelo runtime."""

from __future__ import annotations

import hashlib
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum

from shopman.shop.services.marketing_contracts import ResolvedDispatchArtifact


class ProviderScenario(StrEnum):
    ACCEPT = "accept"
    REJECT = "reject"
    FAIL_BEFORE_CALL = "fail_before_call"
    EFFECT_HAPPENED_RESPONSE_LOST = "effect_happened_response_lost"


@dataclass(frozen=True, slots=True)
class FakeProviderFailure(Exception):
    scenario: ProviderScenario
    effect_happened: bool

    def __str__(self) -> str:
        return self.scenario.value


@dataclass(frozen=True, slots=True)
class FakeProviderResponse:
    accepted: bool
    receipt_ref: str = ""
    rejection_code: str = ""


class FrozenClock:
    """Relógio consciente e avançável, sem patch global de tempo."""

    def __init__(self, instant: datetime):
        if instant.tzinfo is None or instant.utcoffset() is None:
            raise ValueError("FrozenClock exige instante com timezone/offset")
        self._instant = instant

    def now(self) -> datetime:
        return self._instant

    def advance(self, delta: timedelta) -> datetime:
        self._instant += delta
        return self._instant


class ProgrammedProvider:
    """Fornecedor sem rede que distingue os quatro crash modes relevantes.

    ``effects`` representa somente o que o fornecedor pode ter realizado. Uma
    resposta perdida registra o efeito antes de lançar, permitindo provar que o
    chamador não deve repetir a tentativa cegamente.
    """

    def __init__(self, *scenarios: ProviderScenario):
        self._scenarios = deque(scenarios or (ProviderScenario.ACCEPT,))
        self.calls: list[tuple[str, str]] = []
        self.effects: dict[str, str] = {}

    def send(
        self,
        *,
        artifact: ResolvedDispatchArtifact,
        target_key: str,
        idempotency_token: str,
    ) -> FakeProviderResponse:
        if not idempotency_token:
            raise ValueError("idempotency_token é obrigatório no harness")
        scenario = self._scenarios.popleft() if self._scenarios else ProviderScenario.ACCEPT

        if scenario == ProviderScenario.FAIL_BEFORE_CALL:
            raise FakeProviderFailure(scenario=scenario, effect_happened=False)

        self.calls.append((target_key, artifact.artifact_hash))
        receipt_ref = "fake_" + hashlib.sha256(idempotency_token.encode()).hexdigest()[:16]

        if scenario == ProviderScenario.REJECT:
            return FakeProviderResponse(accepted=False, rejection_code="provider_rejected")

        self.effects.setdefault(idempotency_token, receipt_ref)
        if scenario == ProviderScenario.EFFECT_HAPPENED_RESPONSE_LOST:
            raise FakeProviderFailure(scenario=scenario, effect_happened=True)
        return FakeProviderResponse(accepted=True, receipt_ref=receipt_ref)
