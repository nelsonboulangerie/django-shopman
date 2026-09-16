from __future__ import annotations

import uuid
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.test import override_settings
from django.utils import timezone
from shopman.doorman.models import VerificationCode
from shopman.guestman.contrib.identifiers.models import (
    CustomerIdentifier,
    IdentifierType,
)
from shopman.guestman.models import Customer, ExternalIdentity

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


@pytest.mark.parametrize("version", ("invalid", 0, -1))
@override_settings(
    SHOPMAN_PRIVACY_RECEIPT_HMAC_KEY="test-only-privacy-receipt-hmac-key-v1",
    SHOPMAN_PRIVACY_RECEIPT_HMAC_PREVIOUS_KEYS={},
)
def test_privacy_requests_are_unavailable_for_invalid_runtime_key_version(
    settings,
    version,
):
    settings.SHOPMAN_PRIVACY_RECEIPT_HMAC_KEY_VERSION = version

    assert account_privacy.privacy_requests_available() is False
    with pytest.raises(account_privacy.PrivacyReceiptKeyUnavailable):
        account_privacy._current_privacy_key()


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
            receipt.idempotency_fingerprint,
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


def test_delete_account_replays_after_hmac_key_rotation() -> None:
    customer = _customer(suffix="Q")
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
        replay = account_privacy.delete_account(
            customer=customer,
            idempotency_key=idempotency_key,
            authorized_at=timezone.now(),
        )

    assert replay.replayed is True
    assert replay.receipt_ref == first.receipt_ref
    assert PrivacyRequestReceipt.objects.count() == 1


def test_same_idempotency_key_cannot_be_reused_by_another_subject() -> None:
    owner = _customer(suffix="U")
    other = _customer(suffix="V")
    idempotency_key = str(uuid.uuid4())
    account_privacy.delete_account(
        customer=owner,
        idempotency_key=idempotency_key,
        authorized_at=timezone.now(),
    )

    with pytest.raises(account_privacy.PrivacyRequestConflict):
        account_privacy.delete_account(
            customer=other,
            idempotency_key=idempotency_key,
            authorized_at=timezone.now(),
        )

    other.refresh_from_db()
    assert other.is_active is True
    assert PrivacyRequestReceipt.objects.count() == 1


def test_missing_previous_hmac_key_fails_closed_without_second_receipt() -> None:
    customer = _customer(suffix="W")
    idempotency_key = str(uuid.uuid4())
    account_privacy.delete_account(
        customer=customer,
        idempotency_key=idempotency_key,
        authorized_at=timezone.now(),
    )

    with (
        override_settings(
            SHOPMAN_PRIVACY_RECEIPT_HMAC_KEY="test-only-privacy-receipt-hmac-key-v2",
            SHOPMAN_PRIVACY_RECEIPT_HMAC_KEY_VERSION=2,
            SHOPMAN_PRIVACY_RECEIPT_HMAC_PREVIOUS_KEYS={},
        ),
        pytest.raises(account_privacy.PrivacyReceiptKeyUnavailable),
    ):
        assert account_privacy.privacy_requests_available() is False
        account_privacy.delete_account(
            customer=customer,
            idempotency_key=idempotency_key,
            authorized_at=timezone.now(),
        )

    assert PrivacyRequestReceipt.objects.count() == 1


def test_contract_change_keeps_lookup_stable_and_refuses_request_mismatch(monkeypatch) -> None:
    customer = _customer(suffix="X")
    idempotency_key = str(uuid.uuid4())
    account_privacy.delete_account(
        customer=customer,
        idempotency_key=idempotency_key,
        authorized_at=timezone.now(),
    )
    original_fingerprint = PrivacyRequestReceipt.objects.get().idempotency_fingerprint
    monkeypatch.setattr(account_privacy, "_CONTRACT_VERSION", "account-privacy.v2")

    with pytest.raises(account_privacy.PrivacyRequestConflict, match="request_digest_mismatch"):
        account_privacy.delete_account(
            customer=customer,
            idempotency_key=idempotency_key,
            authorized_at=timezone.now(),
        )

    receipt = PrivacyRequestReceipt.objects.get()
    assert receipt.idempotency_fingerprint == original_fingerprint


def test_uncovered_retained_key_blocks_new_delete_and_export_before_receipt_creation() -> None:
    historical = _customer(suffix="Y")
    active = _customer(suffix="Z")
    account_privacy.begin_export(
        customer_uuid=historical.uuid,
        authorized_at=timezone.now(),
    )
    assert PrivacyRequestReceipt.objects.count() == 1

    with override_settings(
        SHOPMAN_PRIVACY_RECEIPT_HMAC_KEY="test-only-privacy-receipt-hmac-key-v2",
        SHOPMAN_PRIVACY_RECEIPT_HMAC_KEY_VERSION=2,
        SHOPMAN_PRIVACY_RECEIPT_HMAC_PREVIOUS_KEYS={},
    ):
        with pytest.raises(account_privacy.PrivacyReceiptKeyUnavailable):
            account_privacy.delete_account(
                customer=active,
                idempotency_key=str(uuid.uuid4()),
                authorized_at=timezone.now(),
            )
        with pytest.raises(account_privacy.PrivacyReceiptKeyUnavailable):
            account_privacy.begin_export(
                customer_uuid=active.uuid,
                authorized_at=timezone.now(),
            )

    active.refresh_from_db()
    assert active.is_active is True
    assert PrivacyRequestReceipt.objects.count() == 1


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


@pytest.mark.parametrize(
    "link_kind",
    ("identifier", "legacy_identity", "source", "metadata"),
)
def test_proven_manychat_link_blocks_before_deletion(link_kind: str) -> None:
    customer = _customer(suffix=f"M{link_kind}")
    if link_kind == "identifier":
        CustomerIdentifier.objects.create(
            customer=customer,
            identifier_type=IdentifierType.MANYCHAT,
            identifier_value=f"manychat-{customer.ref}",
        )
    elif link_kind == "legacy_identity":
        ExternalIdentity.objects.create(
            customer=customer,
            provider=ExternalIdentity.Provider.MANYCHAT,
            provider_uid=f"manychat-{customer.ref}",
        )
    elif link_kind == "source":
        Customer.objects.filter(pk=customer.pk).update(source_system="manychat")
    else:
        Customer.objects.filter(pk=customer.pk).update(
            metadata={"manychat_custom_fields": {"segment": "test"}},
        )

    with pytest.raises(
        account_privacy.AccountDeletionBlocked,
        match="manychat_unlink_required",
    ):
        account_privacy.delete_account(
            customer=customer,
            idempotency_key=str(uuid.uuid4()),
            authorized_at=timezone.now(),
        )

    customer.refresh_from_db()
    receipt = PrivacyRequestReceipt.objects.get()
    assert customer.is_active is True
    assert customer.phone
    assert receipt.state == PrivacyRequestState.FAILED
    assert receipt.failure_stage == "precondition"


def test_pending_manychat_reconciliation_blocks_with_specific_reason() -> None:
    customer = _customer(suffix="MPENDING")
    Customer.objects.filter(pk=customer.pk).update(
        metadata={"manychat_resolution_pending": True},
    )

    with pytest.raises(
        account_privacy.AccountDeletionBlocked,
        match="manychat_reconciliation_pending",
    ):
        account_privacy.delete_account(
            customer=customer,
            idempotency_key=str(uuid.uuid4()),
            authorized_at=timezone.now(),
        )

    customer.refresh_from_db()
    receipt = PrivacyRequestReceipt.objects.get()
    assert customer.is_active is True
    assert customer.phone
    assert receipt.state == PrivacyRequestState.FAILED
    assert receipt.failure_stage == "precondition"


def test_pending_otp_delivery_blocks_until_the_code_delivery_window_closes() -> None:
    customer = _customer(suffix="OTP")
    code = VerificationCode.objects.create(
        target_value=customer.phone,
        customer_id=customer.uuid,
        status=VerificationCode.Status.PENDING,
    )

    with pytest.raises(
        account_privacy.AccountDeletionBlocked,
        match="otp_delivery_in_flight",
    ):
        account_privacy.delete_account(
            customer=customer,
            idempotency_key=str(uuid.uuid4()),
            authorized_at=timezone.now(),
        )

    code.expires_at = timezone.now() - timedelta(seconds=1)
    code.save(update_fields=["expires_at"])
    result = account_privacy.delete_account(
        customer=customer,
        idempotency_key=str(uuid.uuid4()),
        authorized_at=timezone.now(),
    )
    assert result.replayed is False


def test_expired_otp_never_clears_an_independent_manychat_uncertainty() -> None:
    customer = _customer(suffix="OTPMC")
    Customer.objects.filter(pk=customer.pk).update(
        metadata={"manychat_resolution_pending": True},
    )
    VerificationCode.objects.create(
        target_value=customer.phone,
        customer_id=customer.uuid,
        status=VerificationCode.Status.PENDING,
        expires_at=timezone.now() - timedelta(seconds=1),
    )

    with pytest.raises(
        account_privacy.AccountDeletionBlocked,
        match="manychat_reconciliation_pending",
    ):
        account_privacy.delete_account(
            customer=customer,
            idempotency_key=str(uuid.uuid4()),
            authorized_at=timezone.now(),
        )


def test_expired_otp_with_started_delivery_stays_fail_closed() -> None:
    customer = _customer(suffix="OTPSTART")
    VerificationCode.objects.create(
        target_value=customer.phone,
        customer_id=customer.uuid,
        status=VerificationCode.Status.PENDING,
        delivery_started_at=timezone.now() - timedelta(minutes=20),
        expires_at=timezone.now() - timedelta(minutes=10),
    )

    with pytest.raises(
        account_privacy.AccountDeletionBlocked,
        match="otp_delivery_in_flight",
    ):
        account_privacy.delete_account(
            customer=customer,
            idempotency_key=str(uuid.uuid4()),
            authorized_at=timezone.now(),
        )


def test_manychat_link_on_another_customer_does_not_block_by_contact_guess() -> None:
    customer = _customer(suffix="N")
    other = Customer.objects.create(
        ref="CUS-PRIV-MANYCHAT-OTHER",
        first_name="Outra",
        phone="+554399998877",
    )
    CustomerIdentifier.objects.create(
        customer=other,
        identifier_type=IdentifierType.MANYCHAT,
        identifier_value="manychat-other-customer",
    )

    result = account_privacy.delete_account(
        customer=customer,
        idempotency_key=str(uuid.uuid4()),
        authorized_at=timezone.now(),
    )

    assert result.replayed is False
    customer.refresh_from_db()
    other.refresh_from_db()
    assert customer.is_active is False
    assert other.is_active is True
    assert CustomerIdentifier.objects.filter(customer=other).exists()


def test_completed_order_blocks_until_queued_operational_work_is_resolved() -> None:
    from shopman.orderman.models import Directive, Order

    from shopman.shop import directives

    customer = _customer(suffix="I")
    order = Order.objects.create(
        ref="PRIV-COMPLETED-ORDER",
        channel_ref="web",
        session_key="privacy-completed-session",
        handle_type="phone",
        handle_ref=customer.phone,
        status=Order.Status.COMPLETED,
        data={"customer_ref": customer.ref, "customer_phone": customer.phone},
    )
    fiscal = Directive.objects.create(
        topic=directives.FISCAL_EMIT_NFCE,
        payload={
            "order_ref": order.ref,
            "customer_phone": customer.phone,
            "context": {"customer_name": customer.name},
        },
    )
    fulfillment = Directive.objects.create(
        topic=directives.FULFILLMENT_UPDATE,
        payload={"order_ref": order.ref, "recipient_name": customer.name},
    )
    personal_delivery = Directive.objects.create(
        topic=directives.NOTIFICATION_SEND,
        payload={"order_ref": order.ref, "customer_phone": customer.phone},
    )

    original_fiscal_payload = dict(fiscal.payload)
    original_fulfillment_payload = dict(fulfillment.payload)
    original_personal_payload = dict(personal_delivery.payload)

    with pytest.raises(account_privacy.AccountDeletionBlocked, match="order_obligation_pending"):
        account_privacy.delete_account(
            customer=customer,
            idempotency_key=str(uuid.uuid4()),
            authorized_at=timezone.now(),
        )

    fiscal.refresh_from_db()
    fulfillment.refresh_from_db()
    personal_delivery.refresh_from_db()
    customer.refresh_from_db()
    assert fiscal.status == Directive.Status.QUEUED
    assert fiscal.error_code == ""
    assert fiscal.payload == original_fiscal_payload
    assert fulfillment.status == Directive.Status.QUEUED
    assert fulfillment.error_code == ""
    assert fulfillment.payload == original_fulfillment_payload
    assert personal_delivery.status == Directive.Status.QUEUED
    assert personal_delivery.payload == original_personal_payload
    assert customer.is_active is True
    assert customer.phone

    Directive.objects.filter(pk__in=(fiscal.pk, fulfillment.pk)).update(status=Directive.Status.DONE)
    outcome = account_privacy.delete_account(
        customer=customer,
        idempotency_key=str(uuid.uuid4()),
        authorized_at=timezone.now(),
    )

    assert outcome.replayed is False
    fiscal.refresh_from_db()
    fulfillment.refresh_from_db()
    personal_delivery.refresh_from_db()
    assert fiscal.status == Directive.Status.DONE
    assert fulfillment.status == Directive.Status.DONE
    assert personal_delivery.status == Directive.Status.FAILED
    assert personal_delivery.error_code == "subject_deleted"


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
