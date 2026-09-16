from __future__ import annotations

import uuid
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.test import override_settings
from django.utils import timezone
from shopman.guestman.models import Customer

from shopman.shop.models import PrivacyRequestReceipt, PrivacyRequestState
from shopman.shop.services.account import AnonymizationIncomplete
from shopman.storefront.models import (
    CustomerFavorite,
    StockAlertDelivery,
    StockAlertOccurrence,
    StockAlertSubscription,
)
from shopman.storefront.services import account_privacy

pytestmark = pytest.mark.django_db


def _customer(*, suffix: str = "A") -> Customer:
    return Customer.objects.create(
        ref=f"CUS-PRIV-{suffix}",
        first_name="Ana",
        last_name="Silva",
        phone=f"+55439999910{ord(suffix[0]) % 10:02d}",
        email=f"ana-{suffix.lower()}@example.com",
    )


def test_completed_deletion_replays_same_non_pii_receipt() -> None:
    customer = _customer()
    key = str(uuid.uuid4())
    CustomerFavorite.objects.create(customer_ref=customer.ref, sku="PAO-01")
    subscription = StockAlertSubscription.objects.create(
        sku="PAO-01",
        customer_ref=customer.ref,
        contact_phone=customer.phone,
        target_key="a" * 64,
        disclosure_text="Avisar quando estiver disponível",
        disclosure_hash="b" * 64,
        evidence_hash="c" * 64,
        proof_status="verified",
        adult_declared=True,
    )

    first = account_privacy.delete_account(
        customer=customer,
        idempotency_key=key,
        authorized_at=timezone.now(),
    )
    replay = account_privacy.delete_account(
        customer=customer,
        idempotency_key=key,
        authorized_at=timezone.now(),
    )

    assert replay.replayed is True
    assert replay.receipt_ref == first.receipt_ref
    receipt = PrivacyRequestReceipt.objects.get(ref=first.receipt_ref)
    assert receipt.state == PrivacyRequestState.COMPLETED
    serialized = " ".join(
        (
            receipt.subject_digest,
            receipt.idempotency_digest,
            receipt.request_digest,
            str(receipt.outcome_counts),
        )
    )
    assert key not in serialized
    assert "CUS-PRIV-A" not in serialized
    assert "+5543" not in serialized
    assert not CustomerFavorite.objects.filter(customer_ref="CUS-PRIV-A").exists()
    subscription.refresh_from_db()
    assert subscription.customer_ref == ""
    assert subscription.contact_phone == ""
    assert subscription.disclosure_text == ""
    assert subscription.revoked_at is not None
    assert subscription.revoke_reason == "subject_deleted"
    assert subscription.revocation_evidence_hash


def test_different_key_after_completed_deletion_is_a_no_effect_replay() -> None:
    customer = _customer(suffix="F")
    first = account_privacy.delete_account(
        customer=customer,
        idempotency_key=str(uuid.uuid4()),
        authorized_at=timezone.now(),
    )
    second = account_privacy.delete_account(
        customer=customer,
        idempotency_key=str(uuid.uuid4()),
        authorized_at=timezone.now(),
    )

    assert first.replayed is False
    assert second.replayed is True
    assert PrivacyRequestReceipt.objects.filter(state=PrivacyRequestState.COMPLETED).count() == 2
    outcomes = [receipt.outcome_counts for receipt in PrivacyRequestReceipt.objects.order_by("pk")]
    assert {"accounts": 1} in outcomes
    assert {"accounts": 0, "already_deleted": 1} in outcomes


def test_completed_deletion_replays_after_hmac_key_rotation() -> None:
    customer = _customer(suffix="R")
    idempotency_key = str(uuid.uuid4())
    first = account_privacy.delete_account(
        customer=customer,
        idempotency_key=idempotency_key,
        authorized_at=timezone.now(),
    )

    with override_settings(
        SHOPMAN_PRIVACY_RECEIPT_HMAC_KEY="test-only-privacy-receipt-hmac-key-v2",
        SHOPMAN_PRIVACY_RECEIPT_HMAC_KEY_VERSION=2,
        SHOPMAN_PRIVACY_RECEIPT_HMAC_PREVIOUS_KEYS={"1": "test-only-privacy-receipt-hmac-key-v1"},
    ):
        replay = account_privacy.replay_completed_deletion(idempotency_key)

    assert replay is not None
    assert replay.receipt_ref == first.receipt_ref
    receipt = PrivacyRequestReceipt.objects.get(ref=first.receipt_ref)
    assert receipt.key_version == 1


def test_failure_rolls_back_all_mutations_and_keeps_failed_receipt() -> None:
    customer = _customer(suffix="B")
    original_phone = customer.phone
    key = str(uuid.uuid4())

    with (
        patch(
            "shopman.guestman.services.customer.purge_pii",
            side_effect=RuntimeError("database unavailable with private details"),
        ),
        patch("shopman.shop.services.observability.create_operator_alert") as alert,
        pytest.raises(AnonymizationIncomplete, match="purgar PII"),
    ):
        account_privacy.delete_account(
            customer=customer,
            idempotency_key=key,
            authorized_at=timezone.now(),
        )

    customer.refresh_from_db()
    assert customer.is_active is True
    assert customer.phone == original_phone
    receipt = PrivacyRequestReceipt.objects.get()
    assert receipt.state == PrivacyRequestState.FAILED
    assert receipt.failure_stage == "anonymization"
    assert receipt.failure_code == "account_deletion_incomplete"
    assert receipt.completed_at is not None
    assert receipt.retention_until <= timezone.now() + timedelta(days=91)
    assert alert.call_count >= 1
    alert_text = str(alert.call_args)
    assert original_phone not in alert_text
    assert customer.ref not in alert_text
    assert "database unavailable" not in alert_text


def test_active_order_blocks_without_anonymizing_customer() -> None:
    from shopman.orderman.models import Order

    customer = _customer(suffix="C")
    Order.objects.create(
        ref="PRIV-ACTIVE-ORDER",
        channel_ref="web",
        session_key="privacy-active-session",
        handle_type="phone",
        handle_ref=customer.phone,
        status="preparing",
        data={"customer_ref": customer.ref},
    )

    with pytest.raises(account_privacy.AccountDeletionBlocked):
        account_privacy.delete_account(
            customer=customer,
            idempotency_key=str(uuid.uuid4()),
            authorized_at=timezone.now(),
        )

    customer.refresh_from_db()
    assert customer.is_active is True
    assert customer.phone
    receipt = PrivacyRequestReceipt.objects.get()
    assert receipt.state == PrivacyRequestState.FAILED
    assert receipt.failure_stage == "precondition"


def test_stock_alert_delivery_in_flight_blocks_before_any_mutation() -> None:
    customer = _customer(suffix="E")
    subscription = StockAlertSubscription.objects.create(
        sku="PAO-02",
        customer_ref=customer.ref,
        contact_phone=customer.phone,
        target_key="d" * 64,
        evidence_hash="e" * 64,
        proof_status="verified",
        adult_declared=True,
    )
    occurrence = StockAlertOccurrence.objects.create(
        sku="PAO-02",
        event_type="stock_back",
        semantic_key="privacy-in-flight",
        status=StockAlertOccurrence.Status.ELIGIBLE,
    )
    StockAlertDelivery.objects.create(
        subscription=subscription,
        occurrence=occurrence,
        status=StockAlertDelivery.Status.CLAIMED,
    )

    with pytest.raises(account_privacy.AccountDeletionBlocked):
        account_privacy.delete_account(
            customer=customer,
            idempotency_key=str(uuid.uuid4()),
            authorized_at=timezone.now(),
        )

    customer.refresh_from_db()
    subscription.refresh_from_db()
    assert customer.is_active is True
    assert subscription.customer_ref == customer.ref
    assert subscription.revoked_at is None


def test_phone_fallback_does_not_revoke_subscription_owned_by_another_customer() -> None:
    customer = _customer(suffix="G")
    other = _customer(suffix="H")
    subscription = StockAlertSubscription.objects.create(
        sku="PAO-04",
        customer_ref=other.ref,
        contact_phone=customer.phone,
        target_key="i" * 64,
        evidence_hash="j" * 64,
        proof_status="verified",
        adult_declared=True,
    )

    account_privacy.delete_account(
        customer=customer,
        idempotency_key=str(uuid.uuid4()),
        authorized_at=timezone.now(),
    )

    subscription.refresh_from_db()
    assert subscription.customer_ref == other.ref
    assert subscription.contact_phone != ""
    assert subscription.revoked_at is None


@pytest.mark.parametrize("bad_key", ["", "not-a-uuid", str(uuid.UUID(int=0)), str(uuid.uuid1())])
def test_deletion_requires_uuid4_idempotency_key(bad_key: str) -> None:
    customer = _customer(suffix="D")

    with pytest.raises(account_privacy.InvalidIdempotencyKey):
        account_privacy.delete_account(
            customer=customer,
            idempotency_key=bad_key,
            authorized_at=timezone.now(),
        )

    assert not PrivacyRequestReceipt.objects.exists()
