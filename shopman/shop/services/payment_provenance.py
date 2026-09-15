"""Canonical classification of payment confirmations for financial readers."""

from __future__ import annotations

PROVIDER_SIMULATED_CONFIRMATION_MODE = "provider_simulated"


def confirmation_provenance(intent) -> dict[str, object]:
    """Return the small, trusted provider classification persisted on an intent.

    Callers deliberately pass a Payman/adapter intent, never webhook or gateway
    response data.  This keeps financial classification tied to the charge that
    we created rather than to fields supplied by an inbound notification.
    """
    gateway_data = getattr(intent, "gateway_data", None)
    if gateway_data is None:
        gateway_data = getattr(intent, "metadata", None)
    gateway_data = gateway_data or {}
    environment = str(gateway_data.get("provider_environment") or "").strip().lower()
    mode = str(gateway_data.get("confirmation_mode") or "").strip().lower()
    if not environment and not mode:
        return {}
    return {
        "provider_environment": environment,
        "confirmation_mode": mode,
        "is_test_confirmation": mode == PROVIDER_SIMULATED_CONFIRMATION_MODE,
    }


def is_provider_simulated_intent(intent) -> bool:
    """Whether an intent was confirmed by a provider's test simulation."""
    return confirmation_provenance(intent).get("confirmation_mode") == (
        PROVIDER_SIMULATED_CONFIRMATION_MODE
    )


def exclude_provider_simulated(queryset):
    """Exclude test-provider confirmations from real-money aggregates.

    Unmarked intents, local mocks and explicit ``provider_live`` confirmations
    retain their existing meaning. Only the durable marker written by the
    provider adapter removes a row from revenue.
    """
    from django.db.models import Q

    # JSON negation has three-valued SQL semantics on SQLite/PostgreSQL: a
    # plain ``exclude(equal)`` also drops rows where the key is absent/null.
    # Spell the legacy/null branch explicitly so only exact simulation markers
    # disappear.
    return queryset.filter(
        Q(gateway_data__confirmation_mode__isnull=True)
        | ~Q(gateway_data__confirmation_mode=PROVIDER_SIMULATED_CONFIRMATION_MODE),
    )


def exclude_provider_simulated_orders(queryset):
    """Order equivalent used at the canonical BI source boundary."""
    from django.db.models import Q

    return queryset.filter(
        Q(data__payment__confirmation_mode__isnull=True)
        | ~Q(data__payment__confirmation_mode=PROVIDER_SIMULATED_CONFIRMATION_MODE),
    )
