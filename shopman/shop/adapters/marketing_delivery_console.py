"""Hermetic final boundary for a full local Marketing delivery rehearsal.

No contact identity is available here: ``target_key`` is already a protected
HMAC fingerprint.  The adapter performs no network or filesystem I/O and
returns a deterministic receipt so the normal Attempt/Target ledger can be
inspected and replayed exactly like a provider-backed execution.
"""

from __future__ import annotations

import hashlib
import logging

from django.conf import settings

from shopman.shop.services.marketing_contracts import (
    ProviderCallFailure,
    ProviderOutcome,
    ProviderOutcomeKind,
)

SIMULATION_ONLY = True
_EXTERNAL_DEBUG_FLAGS = (
    "SHOPMAN_ALLOW_EXTERNAL_IN_DEBUG",
    "SHOPMAN_SMS_ALLOW_IN_DEBUG",
    "SHOPMAN_MANYCHAT_ALLOW_IN_DEBUG",
    "SHOPMAN_WHATSAPP_ALLOW_IN_DEBUG",
    "SHOPMAN_MACHINE_ALLOW_IN_DEBUG",
)
logger = logging.getLogger(__name__)


def is_available() -> bool:
    """True only for an explicit DEBUG local/test profile with all exits shut."""

    return bool(
        settings.DEBUG
        and getattr(settings, "SHOPMAN_ENVIRONMENT", "")
        in {"development", "test"}
        and getattr(settings, "SHOPMAN_MARKETING_SIMULATION_ENABLED", False)
        and not any(bool(getattr(settings, name, False)) for name in _EXTERNAL_DEBUG_FLAGS)
    )


def send(*, artifact, target_key: str, idempotency_token: str) -> ProviderOutcome:
    """Confirm locally without serializing body, recipient or provider data."""

    if not is_available():
        raise ProviderCallFailure(
            kind=ProviderOutcomeKind.NOT_ATTEMPTED,
            code="local_simulator_disabled",
        )
    digest = hashlib.sha256(
        f"marketing-local-simulation-v1|{idempotency_token}".encode()
    ).hexdigest()
    receipt = f"sim_{digest[:32]}"
    logger.info(
        "marketing.local_simulation_confirmed platform=%s artifact=%s "
        "target=%s receipt=%s external_effect=false",
        artifact.platform,
        artifact.artifact_hash[:12],
        str(target_key)[:12],
        receipt,
    )
    return ProviderOutcome(
        kind=ProviderOutcomeKind.CONFIRMED,
        code="local_simulation_confirmed",
        retryable=False,
        provider_receipt_ref=receipt,
    )


def lookup(
    *,
    target_key: str,
    idempotency_token: str,
    provider_receipt_ref: str,
) -> ProviderOutcome:
    """Resolve an injected local ``unknown`` through a read-only rehearsal."""

    if not is_available():
        raise ProviderCallFailure(
            kind=ProviderOutcomeKind.NOT_ATTEMPTED,
            code="local_simulator_disabled",
        )
    digest = hashlib.sha256(
        f"marketing-local-lookup-v1|{idempotency_token}".encode()
    ).hexdigest()
    receipt = (
        provider_receipt_ref
        if str(provider_receipt_ref).startswith("sim_")
        else f"sim_lookup_{digest[:25]}"
    )
    logger.info(
        "marketing.local_simulation_reconciled target=%s receipt=%s "
        "operation=lookup external_effect=false",
        str(target_key)[:12],
        receipt,
    )
    return ProviderOutcome(
        kind=ProviderOutcomeKind.CONFIRMED,
        code="local_simulation_lookup_confirmed",
        retryable=False,
        provider_receipt_ref=receipt,
    )
