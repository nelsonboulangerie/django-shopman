from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from io import StringIO

import pytest
from django.contrib.auth.models import User
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from shopman.doorman.models import VerificationCode
from shopman.guestman.contrib.consent.models import (
    CommunicationConsent,
    CommunicationConsentEvent,
)
from shopman.guestman.contrib.insights.models import CustomerInsight
from shopman.guestman.models import Customer
from shopman.orderman.models import Order

from shopman.shop.adapters.data_retention import _years_ago
from shopman.shop.management.commands.maintenance_worker import MAINTENANCE_COMMANDS
from shopman.shop.models import (
    CatalogSnapshot,
    Channel,
    Conversation,
    ConversationBinding,
    ConversationMessage,
    DeliveryAttempt,
    DeliveryReconciliation,
    DeliveryTarget,
    OutboundAttempt,
)
from shopman.shop.services.marketing_delivery_ledger import ensure_targets
from shopman.shop.tests.test_marketing_delivery_ledger import _graph


def _run_json() -> tuple[dict[str, object], str]:
    output = StringIO()
    call_command("data_retention", "--json", stdout=output)
    raw = output.getvalue()
    return json.loads(raw), raw


@pytest.mark.django_db
def test_data_retention_default_is_complete_non_mutating_json() -> None:
    with CaptureQueriesContext(connection) as queries:
        payload, _raw = _run_json()

    assert payload["mode"] == "dry-run"
    assert payload["pii"] is False
    assert payload["mutations"] == 0
    assert [row["rule"] for row in payload["rules"]] == [
        f"R{index:02d}" for index in range(1, 16)
    ]
    assert all(isinstance(row["candidates"], int) for row in payload["rules"])
    assert queries
    assert all(
        query["sql"].lstrip().upper().startswith(("SELECT", "WITH"))
        for query in queries
    )


@pytest.mark.django_db
def test_data_retention_refuses_apply_before_any_query_or_mutation(monkeypatch) -> None:
    def must_not_build():
        raise AssertionError("--apply não pode sequer iniciar o inventário")

    monkeypatch.setattr(
        "shopman.shop.management.commands.data_retention.build_retention_dry_run",
        must_not_build,
    )

    with pytest.raises(CommandError, match="gate humano separado"):
        call_command("data_retention", "--apply", stdout=StringIO())


def test_data_retention_does_not_register_new_maintenance_jobs() -> None:
    command_names = {
        item[0] if isinstance(item, tuple) else item for item in MAINTENANCE_COMMANDS
    }

    assert "data_retention" not in command_names
    assert "purge_consent_ip" not in command_names


def test_five_year_cutoff_uses_calendar_years_on_leap_day() -> None:
    leap_day = datetime(2024, 2, 29, 12, tzinfo=UTC)

    assert _years_ago(leap_day, 5) == datetime(
        2019,
        2,
        28,
        12,
        tzinfo=UTC,
    )


@pytest.mark.django_db
def test_r01_uses_the_matching_terminal_milestone_instead_of_created_at() -> None:
    now = timezone.now()
    old = _years_ago(now, 6)
    recent = now - timedelta(days=1)
    recently_completed = Order.objects.create(
        ref="RETENTION-R01-RECENT",
        status=Order.Status.COMPLETED,
        completed_at=recent,
    )
    Order.objects.filter(pk=recently_completed.pk).update(created_at=old)
    Order.objects.create(
        ref="RETENTION-R01-COMPLETED",
        status=Order.Status.COMPLETED,
        completed_at=old,
    )
    Order.objects.create(
        ref="RETENTION-R01-CANCELLED",
        status=Order.Status.CANCELLED,
        cancelled_at=old,
    )
    Order.objects.create(
        ref="RETENTION-R01-RETURNED",
        status=Order.Status.RETURNED,
        returned_at=old,
    )
    Order.objects.create(
        ref="RETENTION-R01-MISSING-MILESTONE",
        status=Order.Status.COMPLETED,
    )

    payload, _raw = _run_json()

    r01 = next(row for row in payload["rules"] if row["rule"] == "R01")
    assert r01["counts"]["pedidos_terminais_apos_prazo"] == 3


@pytest.mark.django_db
def test_uncontracted_personal_inventories_never_become_candidates() -> None:
    old = _years_ago(timezone.now(), 6)
    customer = Customer.objects.create(
        ref="RETENTION-INVENTORY",
        first_name="Dado que não deve sair",
        is_active=False,
    )
    CommunicationConsent.objects.create(
        customer=customer,
        channel="whatsapp",
        status="opted_out",
        revoked_at=old,
    )
    CommunicationConsentEvent.objects.create(
        customer=customer,
        customer_ref_hash="a" * 64,
        channel="whatsapp",
        event_type="revoked",
        resulting_status="opted_out",
        evidence_hash="b" * 64,
        occurred_at=old,
    )
    CustomerInsight.objects.create(customer=customer)

    payload, raw = _run_json()
    rows = {row["rule"]: row for row in payload["rules"]}

    assert rows["R03"]["counts"]["eventos_com_mais_de_cinco_anos"] == 1
    assert rows["R04"]["counts"]["bloqueios_opt_out_com_mais_de_cinco_anos"] == 1
    assert rows["R09"]["counts"]["contas_inativas"] == 1
    assert rows["R13"]["counts"]["perfis_de_contas_inativas"] == 1
    assert all(rows[rule]["candidates"] == 0 for rule in ("R03", "R04", "R09", "R13"))
    assert customer.first_name not in raw


@pytest.mark.django_db
def test_data_retention_counts_expired_code_without_deleting_it() -> None:
    code = VerificationCode.objects.create(target_value="+5500000000000")
    VerificationCode.objects.filter(pk=code.pk).update(
        expires_at=timezone.now() - timedelta(days=8),
    )

    payload, raw = _run_json()

    r10 = next(row for row in payload["rules"] if row["rule"] == "R10")
    assert r10["counts"]["codigos_vencidos"] == 1
    assert code.target_value not in raw
    assert VerificationCode.objects.filter(pk=code.pk).exists()


@pytest.mark.django_db
def test_r05_inventories_expired_links_without_creating_candidates() -> None:
    outbox, members = _graph(suffix="retention-r05", target_keys=("one",))
    first = ensure_targets(outbox.ref, member_ids=[members[0].pk])[0]
    now = timezone.now()
    DeliveryTarget.objects.filter(pk=first.pk).update(
        state=DeliveryTarget.State.CONFIRMED,
        settled_at=now - timedelta(days=91),
        identity_retention_until=now - timedelta(seconds=1),
    )
    second = DeliveryTarget.objects.create(
        outbox=outbox,
        announcement=outbox.announcement,
        snapshot=outbox.snapshot,
        artifact=outbox.artifact,
        member=members[0],
        platform="instagram",
        delivery_kind="publication",
        format="story",
        target_fingerprint="7" * 64,
        fingerprint_key_version=1,
        state=DeliveryTarget.State.CONFIRMED,
        next_attempt_at=now,
        # O vínculo venceu enquanto a entrega ficou pendente e foi assentada só
        # agora. Sem um relógio recalculado no encerramento, não é candidato.
        settled_at=now,
        identity_retention_until=now - timedelta(seconds=1),
        record_retention_until=now + timedelta(days=365),
    )
    DeliveryTarget.objects.create(
        outbox=outbox,
        announcement=outbox.announcement,
        snapshot=outbox.snapshot,
        artifact=outbox.artifact,
        member=members[0],
        platform="facebook",
        delivery_kind="publication",
        format="feed",
        target_fingerprint="8" * 64,
        fingerprint_key_version=1,
        state=DeliveryTarget.State.CONFIRMED,
        next_attempt_at=now,
        settled_at=now,
        identity_retention_until=now + timedelta(days=90),
        record_retention_until=now + timedelta(days=365),
    )

    payload, _raw = _run_json()

    r05 = next(row for row in payload["rules"] if row["rule"] == "R05")
    assert r05["counts"]["vinculos_pessoais"] == 2
    assert r05["candidates"] == 0
    assert (
        DeliveryTarget.objects.filter(
            pk__in=(first.pk, second.pk), member__isnull=False
        ).count()
        == 2
    )


@pytest.mark.django_db
def test_r06_uses_180_days_for_receipt_without_exposing_or_deleting_it() -> None:
    outbox, members = _graph(suffix="retention-r06", target_keys=("one",))
    target = ensure_targets(outbox.ref, member_ids=[members[0].pk])[0]
    now = timezone.now()
    DeliveryTarget.objects.filter(pk=target.pk).update(
        state=DeliveryTarget.State.CONFIRMED,
        settled_at=now - timedelta(days=181),
    )
    attempt = DeliveryAttempt.objects.create(
        target=target,
        ordinal=1,
        state=DeliveryAttempt.State.COMPLETED,
        outcome_kind=DeliveryAttempt.Outcome.CONFIRMED,
        idempotency_token_hash="9" * 64,
        request_hash="a" * 64,
        provider_receipt_ref="provider-receipt-must-not-be-printed",
        started_at=now - timedelta(days=181),
        completed_at=now - timedelta(days=181),
        retention_until=now + timedelta(days=365 * 5),
    )

    payload, raw = _run_json()

    r06 = next(row for row in payload["rules"] if row["rule"] == "R06")
    assert r06["counts"]["recibos_de_tentativa"] == 1
    assert attempt.provider_receipt_ref not in raw
    assert DeliveryAttempt.objects.get(pk=attempt.pk).provider_receipt_ref


@pytest.mark.django_db
def test_r06_excludes_reconciliations_whose_target_is_still_unsettled() -> None:
    now = timezone.now()
    old = now - timedelta(days=181)

    def create_reconciliation(*, suffix: str, target_state: str, receipt: str) -> None:
        outbox, members = _graph(suffix=suffix, target_keys=("one",))
        target = ensure_targets(outbox.ref, member_ids=[members[0].pk])[0]
        DeliveryTarget.objects.filter(pk=target.pk).update(
            state=target_state,
            settled_at=(old if target_state == DeliveryTarget.State.CONFIRMED else None),
        )
        attempt = DeliveryAttempt.objects.create(
            target=target,
            ordinal=1,
            state=DeliveryAttempt.State.COMPLETED,
            outcome_kind=(
                DeliveryAttempt.Outcome.CONFIRMED
                if target_state == DeliveryTarget.State.CONFIRMED
                else DeliveryAttempt.Outcome.UNKNOWN
            ),
            idempotency_token_hash=("c" if target_state == DeliveryTarget.State.CONFIRMED else "d") * 64,
            request_hash=("e" if target_state == DeliveryTarget.State.CONFIRMED else "f") * 64,
            started_at=old,
            completed_at=old,
            retention_until=now + timedelta(days=365),
        )
        DeliveryReconciliation.objects.create(
            command=outbox.command,
            target=target,
            attempt=attempt,
            state=DeliveryReconciliation.State.COMPLETED,
            available_at=old,
            outcome_kind=(
                DeliveryAttempt.Outcome.CONFIRMED
                if target_state == DeliveryTarget.State.CONFIRMED
                else DeliveryAttempt.Outcome.UNKNOWN
            ),
            provider_receipt_ref=receipt,
            completed_at=old,
            retention_until=now + timedelta(days=365),
        )

    create_reconciliation(
        suffix="retention-r06-reconciled",
        target_state=DeliveryTarget.State.CONFIRMED,
        receipt="reconciled-receipt",
    )
    create_reconciliation(
        suffix="retention-r06-unknown",
        target_state=DeliveryTarget.State.UNKNOWN,
        receipt="unknown-receipt",
    )

    payload, raw = _run_json()

    r06 = next(row for row in payload["rules"] if row["rule"] == "R06")
    assert r06["counts"]["recibos_de_reconciliacao"] == 1
    assert "reconciled-receipt" not in raw
    assert "unknown-receipt" not in raw
    assert DeliveryReconciliation.objects.count() == 2


@pytest.mark.django_db
def test_r06_treats_provider_acceptance_as_unsettled_for_concierge() -> None:
    now = timezone.now()
    old = now - timedelta(days=181)
    conversation = Conversation.objects.create(state=Conversation.State.CLOSED)
    binding = ConversationBinding.objects.create(
        conversation=conversation,
        provider="manychat",
        account="retention-concierge",
        transport_channel="whatsapp",
        subject="retention-subject",
        connection_key="retention-r06-connection",
    )
    accepted_message = ConversationMessage.objects.create(
        conversation=conversation,
        binding=binding,
        role=ConversationMessage.Role.ASSISTANT,
        kind=ConversationMessage.Kind.REPLY,
        text="accepted but unsettled",
    )
    delivered_message = ConversationMessage.objects.create(
        conversation=conversation,
        binding=binding,
        role=ConversationMessage.Role.ASSISTANT,
        kind=ConversationMessage.Kind.REPLY,
        text="final delivery",
    )
    OutboundAttempt.objects.create(
        message=accepted_message,
        binding=binding,
        attempt_no=1,
        state=OutboundAttempt.State.ACCEPTED,
        provider_receipt_ref="accepted-receipt",
        payload_hash="1" * 64,
        started_at=old,
        completed_at=old,
    )
    OutboundAttempt.objects.create(
        message=delivered_message,
        binding=binding,
        attempt_no=1,
        state=OutboundAttempt.State.DELIVERED,
        provider_receipt_ref="delivered-receipt",
        payload_hash="2" * 64,
        started_at=old,
        completed_at=old,
    )

    payload, raw = _run_json()

    r06 = next(row for row in payload["rules"] if row["rule"] == "R06")
    assert r06["counts"]["recibos_do_concierge"] == 1
    assert "accepted-receipt" not in raw
    assert "delivered-receipt" not in raw
    assert OutboundAttempt.objects.count() == 2


@pytest.mark.django_db
def test_r12_inventories_0055_raw_snapshot_without_loading_it_into_output() -> None:
    actor = User.objects.create_user("retention-catalog-auditor")
    channel = Channel.objects.create(ref="retention-catalog", name="Catálogo")
    raw_payload = '{"customer_email":"sensitive@example.com"}'
    snapshot = CatalogSnapshot.objects.create(
        channel=channel,
        provider="ifood",
        account_ref="retention-account",
        catalog_ref="retention-catalog",
        context="DEFAULT",
        captured_at=timezone.now(),
        imported_by=actor,
        sha256="a" * 64,
        raw_json=raw_payload,
        source="fixture",
        item_count=1,
    )

    payload, raw = _run_json()

    r12 = next(row for row in payload["rules"] if row["rule"] == "R12")
    assert r12["candidates"] == 0
    assert r12["counts"]["snapshots_de_catalogo_brutos_sem_classificacao"] == 1
    assert "sensitive@example.com" not in raw
    assert CatalogSnapshot.objects.get(pk=snapshot.pk).raw_json == raw_payload


@pytest.mark.django_db
def test_r08_separates_0056_passive_observation_and_never_purges_it() -> None:
    now = timezone.now()
    conversation = Conversation.objects.create(
        state=Conversation.State.CLOSED,
        phone="+5543999990000",
    )
    Conversation.objects.filter(pk=conversation.pk).update(
        updated_at=now - timedelta(days=91),
    )
    binding = ConversationBinding.objects.create(
        conversation=conversation,
        provider="manychat",
        account="retention-account",
        transport_channel="whatsapp",
        subject="sensitive-subject",
        connection_key="retention-connection",
    )
    message = ConversationMessage.objects.create(
        conversation=conversation,
        binding=binding,
        role=ConversationMessage.Role.USER,
        kind=ConversationMessage.Kind.INBOUND,
        text="sensitive observed text",
        envelope={"processing_mode": "observe"},
        automation_eligible=False,
        retention_until=now - timedelta(seconds=1),
    )
    future_message = ConversationMessage.objects.create(
        conversation=conversation,
        binding=binding,
        role=ConversationMessage.Role.USER,
        kind=ConversationMessage.Kind.INBOUND,
        text="future observed text",
        envelope={"processing_mode": "observe"},
        automation_eligible=False,
        retention_until=now + timedelta(days=1),
    )
    legacy_message = ConversationMessage.objects.create(
        conversation=conversation,
        binding=binding,
        role=ConversationMessage.Role.USER,
        kind=ConversationMessage.Kind.INBOUND,
        text="legacy eligible text",
        automation_eligible=True,
        retention_until=None,
    )
    unrelated_message = ConversationMessage.objects.create(
        conversation=conversation,
        binding=binding,
        role=ConversationMessage.Role.USER,
        kind=ConversationMessage.Kind.INBOUND,
        text="not an observation",
        envelope={"processing_mode": "assist"},
        automation_eligible=False,
        retention_until=now - timedelta(seconds=1),
    )

    payload, raw = _run_json()

    r08 = next(row for row in payload["rules"] if row["rule"] == "R08")
    assert r08["counts"] == {"observacoes_passivas_vencidas_0056": 1}
    assert "sensitive observed text" not in raw
    assert "sensitive-subject" not in raw
    assert ConversationMessage.objects.filter(
        pk__in=(
            message.pk,
            future_message.pk,
            legacy_message.pk,
            unrelated_message.pk,
        )
    ).count() == 4
