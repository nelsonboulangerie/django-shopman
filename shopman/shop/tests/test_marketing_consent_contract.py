"""MKT-002+ — contrato de consentimento e supressão do Marketing."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from django.core.exceptions import ValidationError
from shopman.guestman import ConsentService
from shopman.guestman.contrib.consent.models import (
    CommunicationConsent,
    CommunicationConsentEvent,
    ConsentProofStatus,
)
from shopman.guestman.models import Customer

from shopman.shop.services import audience

pytestmark = pytest.mark.django_db


def test_global_optout_suppresses_active_stock_alert_subscription() -> None:
    """A assinatura específica nunca ressuscita um canal globalmente revogado."""

    customer = Customer.objects.create(
        ref="CLI-MKT-OPTOUT",
        first_name="Ana",
        phone="+5543999001001",
    )
    ConsentService.revoke_consent(customer.ref, "whatsapp")

    with patch(
        "shopman.shop.adapters.audience_sources.pending_alert_contacts",
        return_value=[(customer.phone, customer.ref)],
    ):
        resolved = audience.resolve({"alerts": True}, sku="SKU-TESTE")

    assert resolved.total == 0
    assert resolved.all_recipients() == ()


def test_consent_history_is_append_only_and_rebuilds_current_state() -> None:
    customer = Customer.objects.create(
        ref="CLI-MKT-HISTORY",
        first_name="Bia",
        phone="+5543999001002",
    )
    ConsentService.grant_consent(customer.ref, "whatsapp", source="account_preferences")
    ConsentService.revoke_consent(customer.ref, "whatsapp")
    current = ConsentService.grant_consent(
        customer.ref,
        "whatsapp",
        source="explicit_reactivation",
    )

    events = list(
        CommunicationConsentEvent.objects.filter(customer=customer).order_by("occurred_at", "pk")
    )
    assert [event.event_type for event in events] == ["granted", "revoked", "granted"]
    assert all(len(event.evidence_hash) == 64 for event in events)
    assert current.last_event_ref == events[-1].ref
    assert current.is_active is True

    CommunicationConsent.objects.filter(pk=current.pk).update(
        status="opted_out",
        evidence_hash="corrupted-projection",
    )
    rebuilt = ConsentService.rebuild_current_state(customer.ref, "whatsapp")
    assert rebuilt.status == "opted_in"
    assert rebuilt.evidence_hash == events[-1].evidence_hash


def test_consent_event_refuses_update_and_delete() -> None:
    customer = Customer.objects.create(
        ref="CLI-MKT-IMMUTABLE",
        first_name="Caio",
        phone="+5543999001003",
    )
    ConsentService.revoke_consent(customer.ref, "whatsapp")
    event = CommunicationConsentEvent.objects.get(customer=customer)

    event.source = "rewritten"
    with pytest.raises(ValidationError, match="imutáveis"):
        event.save()
    with pytest.raises(ValidationError, match="não podem ser apagados"):
        event.delete()
    with pytest.raises(ValidationError, match="imutáveis"):
        CommunicationConsentEvent.objects.filter(pk=event.pk).update(source="bulk")
    with pytest.raises(ValidationError, match="não podem ser apagados"):
        CommunicationConsentEvent.objects.filter(pk=event.pk).delete()


def test_legacy_unverified_optin_is_not_marketable() -> None:
    customer = Customer.objects.create(
        ref="CLI-MKT-LEGACY",
        first_name="Dani",
        phone="+5543999001004",
    )
    CommunicationConsent.objects.create(
        customer=customer,
        channel="whatsapp",
        status="opted_in",
        proof_status=ConsentProofStatus.LEGACY_UNVERIFIED,
        source="legacy_import",
    )

    assert ConsentService.has_consent(customer.ref, "whatsapp") is False
    assert customer.ref not in ConsentService.get_marketable_customers("whatsapp")


def test_grant_requires_disclosure_text_and_version() -> None:
    customer = Customer.objects.create(
        ref="CLI-MKT-DISCLOSURE",
        first_name="Eva",
        phone="+5543999001005",
    )

    with pytest.raises(ValueError, match="texto e versão"):
        ConsentService.grant_consent(
            customer.ref,
            "whatsapp",
            disclosure_text="",
            disclosure_version="",
        )
    assert CommunicationConsentEvent.objects.filter(customer=customer).count() == 0
