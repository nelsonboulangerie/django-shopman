"""MKT-029: platform configuration is CAS, idempotent and append-only audited."""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.utils import timezone

from shopman.shop.models import (
    MarketingCommandReceipt,
    MarketingPlatformAuditEvent,
    NotificationTemplate,
)
from shopman.shop.services import manychat_flows
from shopman.shop.services.marketing_commands import MarketingCommandConflict
from shopman.shop.services.marketing_platform_configuration import (
    MarketingPlatformUnavailable,
    configure_whatsapp_flow,
    verified_whatsapp_flow_binding,
)
from shopman.shop.services.marketing_security import (
    ACTION_CONFIGURE_PLATFORM,
    authorization_context,
    requirement_for,
)

pytestmark = pytest.mark.django_db

FLOW_A = "content20260909090000_000001"
FLOW_B = "content20260909090000_000002"


def _actor():
    return get_user_model().objects.create_user("platform-owner", password="x")


def _catalog(*flows, state="fresh"):
    now = timezone.now()
    return manychat_flows.FlowCatalog(
        flows=tuple(flows),
        state=state,
        checked_at=now,
        facts_as_of=now if state == "fresh" else now - timedelta(minutes=10),
        fresh_until=(
            now + timedelta(minutes=5)
            if state == "fresh"
            else now - timedelta(minutes=5)
        ),
        catalog_hash="a" * 64,
        reason_code="manychat_catalog_unreachable" if state != "fresh" else "",
    )


def _run(actor, *, flow=FLOW_A, version=1, key="platform-config-key-0001"):
    return configure_whatsapp_flow(
        actor=actor,
        flow_ns=flow,
        base_version=version,
        idempotency_key=key,
        authorize=lambda context, receipt: None,
        request_id="request-platform-1",
    )


def test_platform_change_always_requires_totp_confirmation():
    requirement = requirement_for(
        authorization_context(
            action=ACTION_CONFIGURE_PLATFORM,
            resource_ref="platform:whatsapp",
            base_version=3,
            artifact_hash="a" * 64,
            platforms=("whatsapp",),
            consequence="changes_whatsapp_flow",
        )
    )

    assert requirement.confirmation_mode == "summary"
    assert requirement.step_up_level == "totp"


def test_success_creates_one_versioned_config_receipt_and_audit(monkeypatch):
    actor = _actor()
    monkeypatch.setattr(
        manychat_flows,
        "flow_catalog",
        lambda **kwargs: _catalog((FLOW_A, "Campanha geral")),
    )

    result = _run(actor)

    template = NotificationTemplate.objects.get(event="announcement_published")
    assert template.whatsapp_flow_ns == FLOW_A
    assert template.is_active is True
    assert template.version == 2
    assert "{body}" in template.body
    assert result.receipt.state == MarketingCommandReceipt.State.COMPLETED
    assert result.receipt.resulting_version == 2
    audit = MarketingPlatformAuditEvent.objects.get(command=result.receipt)
    assert audit.previous_flow_ref == ""
    assert audit.resulting_flow_ref == FLOW_A
    assert audit.catalog_hash == "a" * 64
    assert audit.actor == actor


def test_completed_replay_does_not_need_provider_and_does_not_duplicate_audit(monkeypatch):
    actor = _actor()
    catalog = {"value": _catalog((FLOW_A, "Campanha geral"))}
    monkeypatch.setattr(
        manychat_flows,
        "flow_catalog",
        lambda **kwargs: catalog["value"],
    )
    first = _run(actor)
    catalog["value"] = _catalog(state="unavailable")

    replay = _run(actor)

    assert replay.replayed is True
    assert replay.receipt.pk == first.receipt.pk
    assert MarketingPlatformAuditEvent.objects.count() == 1


def test_same_key_with_different_intent_conflicts(monkeypatch):
    actor = _actor()
    monkeypatch.setattr(
        manychat_flows,
        "flow_catalog",
        lambda **kwargs: _catalog(
            (FLOW_A, "Campanha geral"),
            (FLOW_B, "Campanha sazonal"),
        ),
    )
    _run(actor)

    with pytest.raises(MarketingCommandConflict) as caught:
        _run(actor, flow=FLOW_B)

    assert caught.value.code == "idempotency_conflict"
    assert MarketingPlatformAuditEvent.objects.count() == 1


def test_two_stale_version_intents_have_one_winner(monkeypatch):
    actor = _actor()
    monkeypatch.setattr(
        manychat_flows,
        "flow_catalog",
        lambda **kwargs: _catalog(
            (FLOW_A, "Campanha geral"),
            (FLOW_B, "Campanha sazonal"),
        ),
    )
    _run(actor)

    with pytest.raises(MarketingCommandConflict) as caught:
        _run(actor, flow=FLOW_B, key="platform-config-key-0002")

    assert caught.value.code == "version_conflict"
    assert caught.value.current_version == 2
    assert MarketingCommandReceipt.objects.filter(
        state=MarketingCommandReceipt.State.CONFLICT
    ).count() == 1
    assert MarketingPlatformAuditEvent.objects.count() == 1


def test_stale_catalog_cannot_authorize_even_a_known_old_ref(monkeypatch):
    actor = _actor()
    monkeypatch.setattr(
        manychat_flows,
        "flow_catalog",
        lambda **kwargs: _catalog((FLOW_A, "Nome antigo"), state="stale"),
    )

    with pytest.raises(MarketingPlatformUnavailable):
        _run(actor)

    assert NotificationTemplate.objects.count() == 0
    assert MarketingCommandReceipt.objects.count() == 0


def test_platform_audit_is_append_only(monkeypatch):
    actor = _actor()
    monkeypatch.setattr(
        manychat_flows,
        "flow_catalog",
        lambda **kwargs: _catalog((FLOW_A, "Campanha geral")),
    )
    audit = MarketingPlatformAuditEvent.objects.get(command=_run(actor).receipt)

    audit.resulting_flow_ref = FLOW_B
    with pytest.raises(ValidationError):
        audit.save()
    with pytest.raises(ValidationError):
        audit.delete()


def test_verified_binding_seals_exact_fresh_flow_version_and_catalog(monkeypatch):
    NotificationTemplate.objects.create(
        event="announcement_published",
        subject="x",
        body="y",
        whatsapp_flow_ns=FLOW_A,
        version=7,
    )
    monkeypatch.setattr(
        manychat_flows,
        "flow_catalog",
        lambda **kwargs: _catalog((FLOW_A, "Campanha geral")),
    )

    binding = verified_whatsapp_flow_binding(force=True)

    assert binding.flow_name == "Campanha geral"
    assert binding.artifact_payload() == {
        "flow_ref": FLOW_A,
        "flow_version": 7,
        "flow_catalog_hash": "a" * 64,
    }
    assert "flow_ref" not in binding.display_payload()


@pytest.mark.parametrize("state", ["stale", "unavailable"])
def test_verified_binding_never_uses_diagnostic_catalog_as_authority(
    monkeypatch, state
):
    NotificationTemplate.objects.create(
        event="announcement_published",
        subject="x",
        body="y",
        whatsapp_flow_ns=FLOW_A,
    )
    monkeypatch.setattr(
        manychat_flows,
        "flow_catalog",
        lambda **kwargs: _catalog((FLOW_A, "Último nome conhecido"), state=state),
    )

    with pytest.raises(MarketingPlatformUnavailable) as caught:
        verified_whatsapp_flow_binding(force=True)

    assert caught.value.code == "whatsapp_flow_verification_unavailable"
