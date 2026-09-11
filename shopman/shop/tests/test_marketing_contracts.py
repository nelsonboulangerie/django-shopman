"""MKT-001 — contratos executáveis e fornecedor adversarial hermético."""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from shopman.shop.services.marketing_contracts import (
    DeliveryState,
    MarketingContractError,
    ProviderOutcome,
    ProviderOutcomeKind,
    ResolvedDispatchArtifact,
    ensure_delivery_transition,
    iso_with_offset,
)
from shopman.shop.tests.marketing_fakes import (
    FakeProviderFailure,
    FrozenClock,
    ProgrammedProvider,
    ProviderScenario,
)


def _artifact() -> ResolvedDispatchArtifact:
    return ResolvedDispatchArtifact(
        platform="whatsapp",
        body="Croissant saiu do forno.",
        hashtags=("padaria", "feitohoje"),
        link="https://example.test/p/croissant",
        content_version=7,
        facts_hash="f" * 64,
    )


def test_artifact_hash_is_stable_and_contains_no_recipient() -> None:
    first = _artifact()
    second = ResolvedDispatchArtifact(**first.as_payload() | {"hashtags": tuple(first.hashtags)})

    assert first.canonical_bytes() == second.canonical_bytes()
    assert first.artifact_hash == second.artifact_hash
    assert b"phone" not in first.canonical_bytes()
    assert b"target" not in first.canonical_bytes()


def test_error_envelope_has_every_required_key() -> None:
    error = MarketingContractError(
        code="version_conflict",
        detail="O anúncio mudou enquanto você revisava.",
        retryable=False,
        field_errors={"base_version": ("Use a versão atual.",)},
        request_id="req_test_001",
        current_version=8,
    )

    assert error.as_payload() == {
        "code": "version_conflict",
        "detail": "O anúncio mudou enquanto você revisava.",
        "retryable": False,
        "field_errors": {"base_version": ["Use a versão atual."]},
        "request_id": "req_test_001",
        "current_version": 8,
    }


def test_unknown_is_never_retryable_and_cannot_claim_a_receipt() -> None:
    assert ProviderOutcome(
        kind=ProviderOutcomeKind.UNKNOWN,
        code="response_lost",
        retryable=False,
    ).kind == ProviderOutcomeKind.UNKNOWN

    with pytest.raises(ValueError, match="retryable=false"):
        ProviderOutcome(
            kind=ProviderOutcomeKind.UNKNOWN,
            code="response_lost",
            retryable=True,
        )
    with pytest.raises(ValueError, match="não pode inventar receipt"):
        ProviderOutcome(
            kind=ProviderOutcomeKind.UNKNOWN,
            code="response_lost",
            retryable=False,
            provider_receipt_ref="made-up",
        )


def test_delivery_state_machine_blocks_blind_retry_of_unknown() -> None:
    ensure_delivery_transition(DeliveryState.SENDING, DeliveryState.UNKNOWN)
    ensure_delivery_transition(DeliveryState.UNKNOWN, DeliveryState.CONFIRMED)

    with pytest.raises(MarketingContractError) as exc:
        ensure_delivery_transition(DeliveryState.UNKNOWN, DeliveryState.QUEUED)
    assert exc.value.code == "invalid_delivery_transition"


def test_frozen_clock_requires_offset_and_advances_deterministically() -> None:
    instant = datetime(2026, 9, 8, 20, 0, tzinfo=ZoneInfo("America/Sao_Paulo"))
    clock = FrozenClock(instant)

    assert iso_with_offset(clock.now()).endswith("-03:00")
    assert clock.advance(timedelta(hours=12)) == instant + timedelta(hours=12)
    with pytest.raises(ValueError, match="timezone/offset"):
        FrozenClock(datetime(2026, 9, 8, 20, 0))


@pytest.mark.parametrize(
    ("scenario", "effect_happened", "effect_count"),
    [
        (ProviderScenario.FAIL_BEFORE_CALL, False, 0),
        (ProviderScenario.EFFECT_HAPPENED_RESPONSE_LOST, True, 1),
    ],
)
def test_fake_provider_distinguishes_crash_boundary(
    scenario: ProviderScenario,
    effect_happened: bool,
    effect_count: int,
) -> None:
    provider = ProgrammedProvider(scenario)

    with pytest.raises(FakeProviderFailure) as exc:
        provider.send(
            artifact=_artifact(),
            target_key="target_test_001",
            idempotency_token="idem_test_001",
        )

    assert exc.value.effect_happened is effect_happened
    assert len(provider.effects) == effect_count


def test_fake_provider_rejects_without_recording_effect() -> None:
    provider = ProgrammedProvider(ProviderScenario.REJECT)

    response = provider.send(
        artifact=_artifact(),
        target_key="target_test_001",
        idempotency_token="idem_test_001",
    )

    assert response.accepted is False
    assert response.rejection_code == "provider_rejected"
    assert provider.effects == {}


def test_fake_provider_never_uses_network(monkeypatch) -> None:
    def forbidden_network(*_args, **_kwargs):
        raise AssertionError("o harness tentou usar rede")

    monkeypatch.setattr("socket.socket.connect", forbidden_network)
    provider = ProgrammedProvider(ProviderScenario.ACCEPT)

    response = provider.send(
        artifact=_artifact(),
        target_key="target_test_001",
        idempotency_token="idem_test_001",
    )

    assert response.accepted is True
    assert response.receipt_ref.startswith("fake_")
