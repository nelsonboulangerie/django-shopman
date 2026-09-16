from __future__ import annotations

from datetime import timedelta

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.utils import timezone

from shopman.shop.models import (
    PrivacyRequestOperation,
    PrivacyRequestReceipt,
    PrivacyRequestState,
)

pytestmark = pytest.mark.django_db


def _receipt_kwargs(**overrides):
    now = timezone.now()
    values = {
        "operation": PrivacyRequestOperation.EXPORT,
        "subject_digest": "a" * 64,
        "idempotency_digest": "b" * 64,
        "request_digest": "c" * 64,
        "authorization_method": "recent_session",
        "authorized_at": now,
    }
    values.update(overrides)
    return values


def test_receipt_defaults_are_safe_and_support_both_operations() -> None:
    receipt = PrivacyRequestReceipt.objects.create(**_receipt_kwargs())
    deletion = PrivacyRequestReceipt.objects.create(
        **_receipt_kwargs(
            operation=PrivacyRequestOperation.DELETION,
            idempotency_digest="d" * 64,
            request_digest="e" * 64,
        )
    )

    assert receipt.state == PrivacyRequestState.IN_PROGRESS
    assert receipt.completed_at is None
    assert receipt.attempt_count == 1
    assert receipt.key_version == 1
    assert receipt.outcome_counts == {}
    assert receipt.retention_until >= receipt.started_at + timedelta(days=1824)
    assert receipt.retention_until <= receipt.started_at + timedelta(days=1826)
    assert deletion.operation == PrivacyRequestOperation.DELETION

    field_names = {field.name for field in PrivacyRequestReceipt._meta.fields}
    assert field_names.isdisjoint(
        {
            "customer",
            "user",
            "email",
            "phone",
            "idempotency_key",
            "exception",
            "payload",
            "job",
        }
    )


def test_receipt_can_transition_from_in_progress_to_completed() -> None:
    receipt = PrivacyRequestReceipt.objects.create(**_receipt_kwargs())
    completed_at = timezone.now()

    receipt.state = PrivacyRequestState.COMPLETED
    receipt.completed_at = completed_at
    receipt.outcome_counts = {"orders": 2, "addresses": 1}
    receipt.save(update_fields=["state", "completed_at", "outcome_counts", "updated_at"])

    receipt.refresh_from_db()
    assert receipt.state == PrivacyRequestState.COMPLETED
    assert receipt.completed_at == completed_at
    assert receipt.outcome_counts == {"orders": 2, "addresses": 1}


@pytest.mark.parametrize("state", [PrivacyRequestState.COMPLETED, PrivacyRequestState.FAILED])
def test_terminal_state_requires_completed_at(state: str) -> None:
    with pytest.raises(IntegrityError), transaction.atomic():
        PrivacyRequestReceipt.objects.create(**_receipt_kwargs(state=state))


def test_in_progress_state_rejects_completed_at() -> None:
    with pytest.raises(IntegrityError), transaction.atomic():
        PrivacyRequestReceipt.objects.create(**_receipt_kwargs(completed_at=timezone.now()))


def test_operation_subject_and_idempotency_digest_are_unique_together() -> None:
    PrivacyRequestReceipt.objects.create(**_receipt_kwargs())

    with pytest.raises(IntegrityError), transaction.atomic():
        PrivacyRequestReceipt.objects.create(**_receipt_kwargs(request_digest="f" * 64))

    other_operation = PrivacyRequestReceipt.objects.create(
        **_receipt_kwargs(
            operation=PrivacyRequestOperation.DELETION,
            request_digest="f" * 64,
        )
    )
    assert other_operation.operation == PrivacyRequestOperation.DELETION


@pytest.mark.parametrize(
    "field",
    ["subject_digest", "idempotency_digest", "request_digest"],
)
def test_hmac_digests_must_be_opaque_lowercase_hex(field: str) -> None:
    receipt = PrivacyRequestReceipt(**_receipt_kwargs(**{field: "raw-personal-value"}))

    with pytest.raises(ValidationError):
        receipt.full_clean()

    with pytest.raises(IntegrityError), transaction.atomic():
        PrivacyRequestReceipt.objects.create(**_receipt_kwargs(**{field: "raw-personal-value"}))


def test_receipt_constraints_and_query_indexes_exist_in_database() -> None:
    table = PrivacyRequestReceipt._meta.db_table
    with connection.cursor() as cursor:
        constraints = connection.introspection.get_constraints(cursor, table)

    assert constraints["shop_privacy_receipt_operation_idem_uq"]["unique"] is True
    assert constraints["shop_privacy_receipt_terminal_completed_ck"]["check"] is True
    assert constraints["shop_privacy_receipt_hmac_digests_ck"]["check"] is True
    assert constraints["shop_privacy_receipt_attempt_count_ck"]["check"] is True
    assert constraints["shop_privacy_receipt_key_version_ck"]["check"] is True
    assert constraints["shop_privacy_subject_op_idx"]["columns"] == [
        "subject_digest",
        "operation",
    ]
    assert constraints["shop_privacy_state_ret_idx"]["columns"] == [
        "state",
        "retention_until",
    ]
