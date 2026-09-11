"""MKT-002+ — contrato de consentimento e supressão do Marketing."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest
from django.core.exceptions import ValidationError
from shopman.guestman import ConsentService
from shopman.guestman.contrib.consent import service as consent_service
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


def test_audience_source_outage_is_degraded_not_an_authoritative_zero() -> None:
    with patch(
        "shopman.shop.adapters.audience_sources.favorite_customer_refs",
        side_effect=RuntimeError("source unavailable"),
    ):
        resolved = audience.resolve({"favorites": True}, sku="SKU-OUTAGE")

    assert resolved.total == 0
    assert resolved.degraded_sources == ("favorites",)
    assert resolved.summary()["degraded_sources"] == ["favorites"]


def test_audience_normalizes_and_deduplicates_before_hashing() -> None:
    found = [
        audience.Recipient(phone="(43) 99999-0001", customer_ref="CLI-A"),
        audience.Recipient(phone="+55 43 99999-0001", customer_ref="CLI-A"),
    ]
    instant = datetime(2026, 9, 8, 12, 0, tzinfo=ZoneInfo("America/Sao_Paulo"))
    with (
        patch.object(audience, "_chosen_customers", return_value=found),
        patch.object(audience, "_consent_statuses", return_value={"CLI-A": "opted_in"}),
    ):
        resolved = audience.resolve(
            {"customer_refs": ["CLI-A"]},
            now=instant,
        )

    summary = resolved.summary()
    assert [recipient.phone for recipient in resolved.general] == ["+5543999990001"]
    assert summary["eligible_count"] == 1
    assert summary["deduplicated_count"] == 1
    assert summary["policy_version"] == audience.AUDIENCE_POLICY_VERSION
    assert summary["calculated_at"] == instant.isoformat()
    assert len(summary["cohort_hash"]) == 64
    assert "+5543999990001" not in str(summary)


def test_audience_exclusion_counts_close_for_consent_precedence() -> None:
    found = [
        audience.Recipient(phone="+5543999001011", customer_ref="CLI-1"),
        audience.Recipient(phone="+5543999001012", customer_ref="CLI-2"),
        audience.Recipient(phone="+5543999001013", customer_ref="CLI-3"),
    ]
    with (
        patch.object(audience, "_chosen_customers", return_value=found),
        patch.object(
            audience,
            "_consent_statuses",
            return_value={"CLI-1": "opted_in", "CLI-2": "opted_out"},
        ),
    ):
        summary = audience.resolve({"customer_refs": ["CLI-1", "CLI-2", "CLI-3"]}).summary()

    assert summary["eligible_count"] == 1
    assert summary["excluded_by_reason"] == {
        "global_optout": 1,
        "missing_consent": 1,
    }
    assert summary["eligible_count"] + sum(summary["excluded_by_reason"].values()) == 3


def test_consent_outage_fails_closed_and_explains_the_exclusion() -> None:
    found = [audience.Recipient(phone="+5543999001021", customer_ref="CLI-1")]
    with (
        patch.object(audience, "_chosen_customers", return_value=found),
        patch.object(audience, "_consent_statuses", return_value=None),
    ):
        resolved = audience.resolve({"customer_refs": ["CLI-1"]})

    assert resolved.total == 0
    assert resolved.degraded_sources == ("consent",)
    assert resolved.excluded_by_reason == {"consent_unavailable": 1}


def test_large_chosen_cohort_has_constant_query_budget(django_assert_num_queries) -> None:
    refs = []
    for index in range(100):
        ref = f"CLI-MKT-Q-{index:03d}"
        customer = Customer.objects.create(
            ref=ref,
            first_name="Pessoa",
            phone=f"+5543988{index:06d}",
        )
        ConsentService.grant_consent(ref, "whatsapp", source="query-budget")
        refs.append(customer.ref)

    with django_assert_num_queries(2):
        resolved = audience.resolve({"customer_refs": refs})

    assert resolved.total == 100
    assert resolved.degraded_sources == ()


def test_large_cohort_batches_profile_and_consent_parameters(
    django_assert_num_queries, monkeypatch
) -> None:
    refs = []
    for index in range(5):
        ref = f"CLI-MKT-BATCH-{index}"
        customer = Customer.objects.create(
            ref=ref,
            first_name="Pessoa",
            phone=f"+55439770000{index}",
        )
        ConsentService.grant_consent(ref, "whatsapp", source="batch-budget")
        refs.append(customer.ref)

    monkeypatch.setattr(audience, "AUDIENCE_LOOKUP_BATCH_SIZE", 2)
    monkeypatch.setattr(consent_service, "CONSENT_STATUS_BATCH_SIZE", 2)

    with django_assert_num_queries(6):
        resolved = audience.resolve({"customer_refs": refs})

    assert {recipient.customer_ref for recipient in resolved.general} == set(refs)
