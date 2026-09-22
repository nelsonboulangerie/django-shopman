"""Canonical classification of payment confirmations for financial readers."""

from __future__ import annotations

PROVIDER_SIMULATED_CONFIRMATION_MODE = "provider_simulated"
PROVIDER_LIVE_CONFIRMATION_MODE = "provider_live"

#: O simulador local (``payment_mock``) não tem provedor: o "ambiente" dele é a
#: própria instância. O rótulo existe para a auditoria dizer DE ONDE veio a
#: simulação; quem decide receita é só ``confirmation_mode``.
LOCAL_MOCK_ENVIRONMENT = "local_mock"


def provenance_stamp(*, environment: str, simulated: bool) -> dict[str, str]:
    """A marca que todo adapter grava no intent ANTES de qualquer confirmação.

    Uma régua só para Efí homologação, Stripe em chave de teste e o simulador
    local: quem não recebe dinheiro de verdade nasce ``provider_simulated``, e os
    leitores financeiros (fechamento, livro do turno, B.I., conciliação, porta
    fiscal) excluem pela mesma chave, sem saber qual provedor a escreveu.
    """
    return {
        "provider_environment": environment,
        "confirmation_mode": (
            PROVIDER_SIMULATED_CONFIRMATION_MODE if simulated else PROVIDER_LIVE_CONFIRMATION_MODE
        ),
    }


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
    """Exclude simulated confirmations from real-money aggregates.

    Unmarked (legacy) intents and explicit ``provider_live`` confirmations
    retain their existing meaning. Only the durable marker written by the
    adapter removes a row from revenue — Efí sandbox, Stripe test keys and the
    local ``payment_mock`` all write it at intent creation.
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


def is_simulated_order_payment(order) -> bool:
    """O pagamento deste pedido foi simulado (nenhum dinheiro entrou)?

    Lê a cópia da marca em ``Order.data["payment"]``, gravada pelo
    ``_persist_intent`` a partir do intent — a mesma chave que o B.I. filtra.
    """
    payment = ((getattr(order, "data", None) or {}).get("payment") or {})
    if not isinstance(payment, dict):
        return False
    return str(payment.get("confirmation_mode") or "").strip().lower() == (
        PROVIDER_SIMULATED_CONFIRMATION_MODE
    )


def exclude_provider_simulated_orders(queryset):
    """Order equivalent used at the canonical BI source boundary."""
    from django.db.models import Q

    return queryset.filter(
        Q(data__payment__confirmation_mode__isnull=True)
        | ~Q(data__payment__confirmation_mode=PROVIDER_SIMULATED_CONFIRMATION_MODE),
    )
