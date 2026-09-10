"""Local rehearsal proves the production graph without a provider side effect."""

from __future__ import annotations

from datetime import datetime
from io import StringIO
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import override_settings
from shopman.orderman.models import Directive

from shopman.shop.adapters import marketing_delivery_console
from shopman.shop.models import (
    Announcement,
    AnnouncementDeliveryState,
    AnnouncementStatus,
    DeliveryAttempt,
    DeliveryReconciliation,
    DeliveryTarget,
    MarketingOutbox,
)
from shopman.shop.services import manychat_flows, manychat_marketing_safety, marketing_time
from shopman.shop.services.marketing_approval import PUBLISH_NOW, approve_command
from shopman.shop.services.marketing_contracts import (
    MarketingContractError,
    ProviderCallFailure,
    ProviderOutcomeKind,
    ResolvedDispatchArtifact,
)
from shopman.shop.services.marketing_delivery_recovery import (
    request_reconciliation_command,
)

SIMULATOR_SETTINGS = {
    "DEBUG": True,
    "SHOPMAN_ENVIRONMENT": "development",
    "SHOPMAN_MARKETING_OUTBOX_CONSUMER_ENABLED": True,
    "SHOPMAN_MARKETING_DELIVERY_CONSUMER_ENABLED": True,
    "SHOPMAN_MARKETING_SIMULATION_ENABLED": True,
    "SHOPMAN_MARKETING_DELIVERY_ADAPTERS": dict.fromkeys(("instagram", "facebook", "google_business", "whatsapp"), "shopman.shop.adapters.marketing_delivery_console"),
    "SHOPMAN_ALLOW_EXTERNAL_IN_DEBUG": False,
    "SHOPMAN_SMS_ALLOW_IN_DEBUG": False,
    "SHOPMAN_MANYCHAT_ALLOW_IN_DEBUG": False,
    "SHOPMAN_WHATSAPP_ALLOW_IN_DEBUG": False,
    "SHOPMAN_MACHINE_ALLOW_IN_DEBUG": False,
}
SIMULATION_AFFORDANCES = {
    **SIMULATOR_SETTINGS,
    "SHOPMAN_MARKETING_SIMULATION_IGNORE_QUIET_HOURS": True,
    "SHOPMAN_MARKETING_SIMULATION_FLOWS": (
        ("local_marketing_e2e", "Fluxo local — sem envio externo"),
    ),
}


def _artifact() -> ResolvedDispatchArtifact:
    return ResolvedDispatchArtifact(
        platform="instagram",
        body="Conteúdo que jamais deve aparecer no log",
        content_version=2,
    )


@pytest.mark.django_db
def test_simulator_refuses_every_non_explicit_or_hybrid_profile(settings):
    settings.SHOPMAN_MARKETING_SIMULATION_ENABLED = False
    assert marketing_delivery_console.is_available() is False

    settings.SHOPMAN_MARKETING_SIMULATION_ENABLED = True
    settings.DEBUG = True
    settings.SHOPMAN_ENVIRONMENT = "development"
    settings.SHOPMAN_ALLOW_EXTERNAL_IN_DEBUG = True
    assert marketing_delivery_console.is_available() is False

    with pytest.raises(ProviderCallFailure) as caught:
        marketing_delivery_console.send(
            artifact=_artifact(),
            target_key="a" * 64,
            idempotency_token="marketing:v1:target:attempt:1",
        )
    assert caught.value.kind == ProviderOutcomeKind.NOT_ATTEMPTED
    assert caught.value.code == "local_simulator_disabled"


@pytest.mark.django_db
@override_settings(**SIMULATOR_SETTINGS)
def test_simulator_receipt_is_deterministic_and_log_is_pii_free(caplog):
    artifact = _artifact()
    kwargs = {
        "artifact": artifact,
        "target_key": "b" * 64,
        "idempotency_token": "marketing:v1:target:attempt:1",
    }

    first = marketing_delivery_console.send(**kwargs)
    second = marketing_delivery_console.send(**kwargs)

    assert first == second
    assert first.kind == ProviderOutcomeKind.CONFIRMED
    assert first.provider_receipt_ref.startswith("sim_")
    assert "Conteúdo que jamais" not in caplog.text


@pytest.mark.django_db
@override_settings(**SIMULATOR_SETTINGS)
def test_simulator_lookup_is_deterministic_read_only_and_pii_free():
    kwargs = {
        "target_key": "c" * 64,
        "idempotency_token": "marketing:v1:target:attempt:1",
        "provider_receipt_ref": "",
    }

    with patch.object(marketing_delivery_console.logger, "info") as logged:
        first = marketing_delivery_console.lookup(**kwargs)
        second = marketing_delivery_console.lookup(**kwargs)

    assert first == second
    assert first.kind == ProviderOutcomeKind.CONFIRMED
    assert first.provider_receipt_ref.startswith("sim_lookup_")
    assert logged.call_count == 2
    assert "operation=lookup external_effect=false" in logged.call_args.args[0]
    assert "c" * 64 not in repr(logged.call_args)


@pytest.mark.django_db
@override_settings(
    **{
        **SIMULATOR_SETTINGS,
        "SHOPMAN_MARKETING_DELIVERY_ADAPTERS": {
            "instagram": "shopman.shop.adapters.marketing_delivery_console",
        },
    }
)
def test_delivery_adapter_never_falls_back_across_platforms():
    from shopman.shop.services.marketing_delivery_runtime import delivery_provider

    assert delivery_provider("instagram") is marketing_delivery_console
    assert delivery_provider("facebook") is None


@override_settings(**SIMULATION_AFFORDANCES)
def test_hermetic_profile_can_rehearse_quiet_hours_and_flow_sealing():
    window = marketing_time.delivery_window(
        datetime.fromisoformat("2026-09-09T21:00:00-03:00"),
        timezone_name="America/Sao_Paulo",
    )
    catalog = manychat_flows._fetch()

    assert window.allowed is True
    assert catalog.state == "fresh"
    assert catalog.flows == (
        ("local_marketing_e2e", "Fluxo local — sem envio externo"),
    )
    manychat_marketing_safety.require_safe_delivery()


@override_settings(
    **{
        **SIMULATION_AFFORDANCES,
        "SHOPMAN_MARKETING_DELIVERY_ADAPTERS": {},
    }
)
def test_simulation_flags_alone_cannot_suspend_real_safety_gates():
    window = marketing_time.delivery_window(
        datetime.fromisoformat("2026-09-09T21:00:00-03:00"),
        timezone_name="America/Sao_Paulo",
    )
    catalog = manychat_flows._fetch()

    assert window.allowed is False
    assert catalog.state == "not_configured"
    with pytest.raises(MarketingContractError) as caught:
        manychat_marketing_safety.require_safe_delivery()
    assert caught.value.code == "manychat_custom_fields_unverified"


@pytest.mark.django_db(transaction=True)
@override_settings(**SIMULATOR_SETTINGS)
def test_approval_reaches_confirmed_ledger_receipt_through_the_real_runtime():
    actor = get_user_model().objects.create_user(
        username="local-simulation-operator",
        password="irrelevant",
    )
    announcement = Announcement.objects.create(
        status=AnnouncementStatus.PENDING_REVIEW,
        content={"body": "Fornada pronta"},
        platforms=["instagram"],
    )
    approved = approve_command(
        announcement.pk,
        actor=actor,
        idempotency_key="local-simulation-e2e-approval",
        base_version=1,
        publish_mode=PUBLISH_NOW,
        content={"body": "Fornada pronta"},
        platform_content={},
        platforms=["instagram"],
    )
    output = StringIO()

    call_command(
        "process_marketing_delivery",
        with_outbox=True,
        worker_id="local-simulation-e2e",
        stdout=output,
    )

    announcement.refresh_from_db()
    outbox = MarketingOutbox.objects.get(command=approved.receipt)
    directive = Directive.objects.get(dedupe_key=f"marketing-outbox:{outbox.ref}")
    target = DeliveryTarget.objects.get(outbox=outbox)
    attempt = DeliveryAttempt.objects.get(target=target)
    assert outbox.state == MarketingOutbox.State.DISPATCHED
    assert directive.status == Directive.Status.DONE
    assert outbox.fanout_expected == outbox.fanout_materialized == 1
    assert outbox.fanout_completed_at is not None
    assert target.state == DeliveryTarget.State.CONFIRMED
    assert target.member_id is None
    assert target.provider_receipt_ref.startswith("sim_")
    assert attempt.state == DeliveryAttempt.State.COMPLETED
    assert attempt.outcome_kind == ProviderOutcomeKind.CONFIRMED
    assert announcement.delivery_state == AnnouncementDeliveryState.SUCCEEDED
    assert announcement.status == AnnouncementStatus.SETTLED
    assert "confirmed=1" in output.getvalue()


@pytest.mark.django_db(transaction=True)
@override_settings(**SIMULATOR_SETTINGS)
def test_unknown_reaches_lookup_only_reconciliation_through_local_runtime():
    actor = get_user_model().objects.create_user(
        username="local-reconciliation-operator",
        password="irrelevant",
    )
    announcement = Announcement.objects.create(
        status=AnnouncementStatus.PENDING_REVIEW,
        content={"body": "Fornada pronta"},
        platforms=["instagram"],
    )
    approve_command(
        announcement.pk,
        actor=actor,
        idempotency_key="local-reconciliation-approval",
        base_version=1,
        publish_mode=PUBLISH_NOW,
        content={"body": "Fornada pronta"},
        platform_content={},
        platforms=["instagram"],
    )
    call_command(
        "process_marketing_delivery",
        with_outbox=True,
        worker_id="local-reconciliation-send",
        stdout=StringIO(),
    )
    target = DeliveryTarget.objects.get(announcement=announcement)
    attempt = DeliveryAttempt.objects.get(target=target)
    target.state = DeliveryTarget.State.UNKNOWN
    target.provider_receipt_ref = ""
    target.last_error_code = "response_lost"
    target.settled_at = None
    target.save(update_fields=[
        "state",
        "provider_receipt_ref",
        "last_error_code",
        "settled_at",
    ])
    attempt.outcome_kind = ProviderOutcomeKind.UNKNOWN
    attempt.provider_receipt_ref = ""
    attempt.error_code = "response_lost"
    attempt.save(update_fields=[
        "outcome_kind",
        "provider_receipt_ref",
        "error_code",
    ])
    announcement.refresh_from_db()
    request_reconciliation_command(
        announcement.pk,
        actor=actor,
        idempotency_key="local-reconciliation-command",
        base_version=announcement.version,
    )
    output = StringIO()

    call_command(
        "process_marketing_delivery",
        with_reconciliation=True,
        worker_id="local-reconciliation-lookup",
        stdout=output,
    )

    target.refresh_from_db()
    reconciliation = DeliveryReconciliation.objects.get(target=target)
    assert target.state == DeliveryTarget.State.CONFIRMED
    assert target.provider_receipt_ref.startswith("sim_lookup_")
    assert reconciliation.state == DeliveryReconciliation.State.COMPLETED
    assert reconciliation.outcome_kind == ProviderOutcomeKind.CONFIRMED
    assert "reconciliations=confirmed=1" in output.getvalue()
