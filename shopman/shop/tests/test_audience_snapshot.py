"""MKT-006 — sealed private cohort with subtract-only revalidation."""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone
from shopman.guestman import ConsentService
from shopman.guestman.models import Customer

from shopman.shop.models import AudienceSnapshot, AudienceSnapshotMember
from shopman.shop.services import audience, audience_snapshot
from shopman.shop.services.marketing_contracts import MarketingContractError
from shopman.storefront.services import stock_alerts

pytestmark = pytest.mark.django_db


def _customer(ref: str, phone: str, *, opted_in: bool) -> Customer:
    customer = Customer.objects.create(ref=ref, first_name="Ana", phone=phone)
    if opted_in:
        ConsentService.grant_consent(ref, "whatsapp", source="snapshot-test")
    return customer


def test_snapshot_persists_only_protected_identity_and_sanitized_rules() -> None:
    customer = _customer("CLI-SNAP-1", "+5543999002001", opted_in=True)
    rules = {"customer_refs": [customer.ref], "match": "any"}
    resolved = audience.resolve(rules)

    snapshot = audience_snapshot.create_snapshot(resolved, rules=rules)
    member = snapshot.members.get()

    assert member.customer_id == customer.pk
    assert member.subscription_ref is None
    assert len(member.target_key) == 64
    assert "phone" not in {field.name for field in AudienceSnapshotMember._meta.fields}
    assert snapshot.rule_summary == {"customer_refs_count": 1, "match": "any"}
    serialized = str({**snapshot.summary, **snapshot.rule_summary})
    assert customer.phone not in serialized
    assert customer.ref not in serialized


def test_snapshot_never_grows_after_a_late_optin() -> None:
    eligible = _customer("CLI-SNAP-2", "+5543999002002", opted_in=True)
    late = _customer("CLI-SNAP-3", "+5543999002003", opted_in=False)
    rules = {"customer_refs": [eligible.ref, late.ref]}
    snapshot = audience_snapshot.create_snapshot(audience.resolve(rules), rules=rules)
    assert snapshot.members.count() == 1

    ConsentService.grant_consent(late.ref, "whatsapp", source="late-optin")
    materialized = audience_snapshot.materialize_active_recipients(snapshot)

    assert [recipient.customer_ref for recipient in materialized.recipients] == [eligible.ref]
    assert snapshot.members.count() == 1


def test_revocation_after_snapshot_subtracts_before_contact_materialization() -> None:
    customer = _customer("CLI-SNAP-4", "+5543999002004", opted_in=True)
    rules = {"customer_refs": [customer.ref]}
    snapshot = audience_snapshot.create_snapshot(audience.resolve(rules), rules=rules)
    ConsentService.revoke_consent(customer.ref, "whatsapp")

    materialized = audience_snapshot.materialize_active_recipients(snapshot)

    assert materialized.recipients == ()
    assert materialized.excluded_by_reason == {"global_optout": 1}


def test_customer_phone_is_late_bound_without_changing_snapshot_membership() -> None:
    customer = _customer("CLI-SNAP-5", "+5543999002005", opted_in=True)
    rules = {"customer_refs": [customer.ref]}
    snapshot = audience_snapshot.create_snapshot(audience.resolve(rules), rules=rules)
    Customer.objects.filter(pk=customer.pk).update(phone="+5543999002999")

    recipients = audience_snapshot.materialize_active_recipients(snapshot).recipients

    assert [recipient.phone for recipient in recipients] == ["+5543999002999"]
    assert snapshot.members.count() == 1


def test_anonymous_subscription_is_late_bound_and_revocable() -> None:
    sub = stock_alerts.subscribe("SKU-SNAPSHOT", phone="+5543999002006")
    rules = {"alerts": True}
    snapshot = audience_snapshot.create_snapshot(
        audience.resolve(rules, sku=sub.sku),
        rules=rules,
    )
    member = snapshot.members.get()
    assert member.customer_id is None
    assert member.subscription_ref == sub.ref

    stock_alerts.revoke(sub.ref, sku=sub.sku, phone=sub.contact_phone)
    materialized = audience_snapshot.materialize_active_recipients(snapshot)

    assert materialized.recipients == ()
    assert materialized.excluded_by_reason == {"subscription_inactive": 1}


def test_degraded_or_stale_resolution_cannot_be_sealed() -> None:
    now = timezone.now()
    degraded = audience.AudienceResult(
        degraded_sources=("consent",),
        calculated_at=now,
        expires_at=now + timedelta(minutes=15),
    )
    stale = audience.AudienceResult(
        calculated_at=now - timedelta(minutes=20),
        expires_at=now - timedelta(minutes=5),
    )

    with pytest.raises(MarketingContractError) as degraded_error:
        audience_snapshot.create_snapshot(degraded, rules={}, now=now)
    with pytest.raises(MarketingContractError) as stale_error:
        audience_snapshot.create_snapshot(stale, rules={}, now=now)

    assert degraded_error.value.code == "audience_degraded"
    assert stale_error.value.code == "audience_preview_expired"
    assert AudienceSnapshot.objects.count() == 0
