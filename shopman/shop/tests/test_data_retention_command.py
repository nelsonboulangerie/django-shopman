from __future__ import annotations

import json
from datetime import timedelta
from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.utils import timezone
from shopman.doorman.models import VerificationCode

from shopman.shop.models import DeliveryAttempt, DeliveryTarget
from shopman.shop.services.marketing_delivery_ledger import ensure_targets
from shopman.shop.tests.test_marketing_delivery_ledger import _graph


@pytest.mark.django_db
def test_data_retention_default_is_complete_non_mutating_json() -> None:
    output = StringIO()

    call_command("data_retention", "--json", stdout=output)

    payload = json.loads(output.getvalue())
    assert payload["mode"] == "dry-run"
    assert payload["pii"] is False
    assert payload["mutations"] == 0
    assert [row["rule"] for row in payload["rules"]] == [
        f"R{index:02d}" for index in range(1, 16)
    ]
    assert all(isinstance(row["candidates"], int) for row in payload["rules"])


@pytest.mark.django_db
def test_data_retention_refuses_apply_before_separate_gate() -> None:
    with pytest.raises(CommandError, match="gate humano separado"):
        call_command("data_retention", "--apply", stdout=StringIO())


@pytest.mark.django_db
def test_data_retention_counts_expired_code_without_deleting_it() -> None:
    code = VerificationCode.objects.create(target_value="+5500000000000")
    VerificationCode.objects.filter(pk=code.pk).update(
        expires_at=timezone.now() - timedelta(days=8),
    )
    output = StringIO()

    call_command("data_retention", "--dry-run", "--json", stdout=output)

    payload = json.loads(output.getvalue())
    r10 = next(row for row in payload["rules"] if row["rule"] == "R10")
    assert r10["counts"]["codigos_vencidos"] == 1
    assert VerificationCode.objects.filter(pk=code.pk).exists()


@pytest.mark.django_db
def test_r05_counts_each_expired_personal_link_without_selecting_future_links() -> None:
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
        target_fingerprint="7" * 64,
        fingerprint_key_version=1,
        state=DeliveryTarget.State.CONFIRMED,
        next_attempt_at=now,
        settled_at=now - timedelta(days=91),
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
        target_fingerprint="8" * 64,
        fingerprint_key_version=1,
        state=DeliveryTarget.State.CONFIRMED,
        next_attempt_at=now,
        settled_at=now,
        identity_retention_until=now + timedelta(days=90),
        record_retention_until=now + timedelta(days=365),
    )

    output = StringIO()
    call_command("data_retention", "--json", stdout=output)

    r05 = next(row for row in json.loads(output.getvalue())["rules"] if row["rule"] == "R05")
    assert r05["counts"]["vinculos_pessoais"] == 2
    assert DeliveryTarget.objects.filter(pk__in=(first.pk, second.pk), member__isnull=False).count() == 2


@pytest.mark.django_db
def test_r06_uses_180_days_for_receipt_not_the_five_year_record_retention() -> None:
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
    output = StringIO()

    call_command("data_retention", "--json", stdout=output)

    payload = json.loads(output.getvalue())
    r06 = next(row for row in payload["rules"] if row["rule"] == "R06")
    assert r06["counts"]["recibos_de_tentativa"] == 1
    assert "provider-receipt-must-not-be-printed" not in output.getvalue()
    assert DeliveryAttempt.objects.get(pk=attempt.pk).provider_receipt_ref
