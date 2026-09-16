from __future__ import annotations

import json
import tempfile
from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from shopman.doorman.models import CustomerUser, TrustedDevice, VerificationCode
from shopman.guestman.contrib.loyalty.models import LoyaltyAccount, LoyaltyTransaction
from shopman.guestman.contrib.preferences.models import CustomerPreference
from shopman.guestman.models import Customer, CustomerAddress
from shopman.orderman.models import Order, OrderItem

from shopman.shop.models import (
    Announcement,
    AudienceSnapshot,
    AudienceSnapshotMember,
    Conversation,
    ConversationBinding,
    ConversationMessage,
)
from shopman.storefront.models import CustomerFavorite, StockAlertSubscription
from shopman.storefront.services import account_export

pytestmark = pytest.mark.django_db


def _customer(*, suffix: str = "01") -> Customer:
    return Customer.objects.create(
        ref=f"EXPORT-{suffix}",
        first_name="Ana",
        last_name="Exportação",
        phone=f"+5543999990{suffix}",
        email=f"ana-{suffix}@example.com",
        metadata={
            "preferences": "sem lactose",
            "fiscal_prefs": {"cpf_na_nota": True, "email_receipt": False},
            "access_token": "must-not-leak",
            "accessToken": "also-must-not-leak",
            "nested": {"secret": "also-must-not-leak", "safe": "kept"},
        },
    )


def _decoded_export(customer: Customer, **kwargs):
    artifact = account_export.build_account_export(customer, **kwargs)
    assert artifact.tell() == 0
    byte_count = artifact.byte_count
    section_counts = artifact.section_counts
    payload = json.load(artifact)
    assert byte_count == artifact.tell()
    artifact.close()
    return payload, section_counts


def _all_keys(value):
    if isinstance(value, dict):
        for key, child in value.items():
            yield key
            yield from _all_keys(child)
    elif isinstance(value, list):
        for child in value:
            yield from _all_keys(child)


def test_export_is_complete_incremental_and_has_no_legacy_caps():
    customer = _customer()
    CustomerAddress.objects.create(
        customer=customer,
        label="home",
        formatted_address="Rua das Flores, 10",
        city="Londrina",
        state_code="PR",
    )
    CustomerPreference.objects.create(
        customer=customer,
        category="dietary",
        key="sem_lactose",
        value=True,
    )

    orders = [
        Order(
            ref=f"EXP-ORDER-{index:03d}",
            channel_ref="web",
            handle_type="phone",
            handle_ref=customer.phone,
            status="completed",
            data={"customer_ref": customer.ref},
            total_q=index,
        )
        for index in range(205)
    ]
    Order.objects.bulk_create(orders)
    first_order = Order.objects.order_by("pk").first()
    OrderItem.objects.create(
        order=first_order,
        line_id="line-1",
        sku="PAO-01",
        name="Pão francês",
        qty=2,
        unit_price_q=100,
        line_total_q=200,
        meta={"customer_note": "bem assado", "token": "not-exported"},
    )

    loyalty = LoyaltyAccount.objects.create(customer=customer, points_balance=105, lifetime_points=105)
    LoyaltyTransaction.objects.bulk_create(
        [
            LoyaltyTransaction(
                account=loyalty,
                transaction_type="earn",
                points=1,
                balance_after=index + 1,
                description=f"Compra {index}",
                reference=f"order:{index}",
            )
            for index in range(105)
        ]
    )

    conversation = Conversation.objects.create(
        customer_ref=customer.ref,
        customer_name=customer.name,
        phone=customer.phone,
        channel_ref="whatsapp",
    )
    binding = ConversationBinding.objects.create(
        conversation=conversation,
        provider="synthetic",
        account="export-test",
        transport_channel="whatsapp",
        subject=customer.phone,
        connection_key="export-test",
        status=ConversationBinding.Status.ACTIVE,
    )
    message = ConversationMessage.objects.create(
        conversation=conversation,
        binding=binding,
        role="user",
        kind="inbound",
        text="Prefiro retirar depois das 17h",
        content=[
            {"type": "text", "text": "Prefiro retirar depois das 17h"},
            {"type": "tool_result", "authorization": "must-not-leak"},
        ],
    )
    CustomerFavorite.objects.create(customer_ref=customer.ref, sku="PAO-01")
    StockAlertSubscription.objects.create(
        sku="PAO-01",
        customer_ref=customer.ref,
        contact_phone=customer.phone,
        target_key="target-protected",
        disclosure_text="Avisar quando sair do forno",
        evidence_hash="e" * 64,
        proof_status="verified",
        adult_declared=True,
    )

    announcement = Announcement.objects.create(content={"body": "Fornada pronta"})
    now = timezone.now()
    snapshot = AudienceSnapshot.objects.create(
        announcement=announcement,
        summary={"total": 1},
        rule_summary={},
        rule_hash="1" * 64,
        cohort_hash="2" * 64,
        policy_version="marketing-audience.v1",
        calculated_at=now,
        expires_at=now + timedelta(minutes=5),
        retention_until=now + timedelta(days=90),
    )
    AudienceSnapshotMember.objects.create(
        snapshot=snapshot,
        customer=customer,
        target_key="3" * 64,
        reasons=["consent"],
    )

    payload, counts = _decoded_export(customer, spool_max_size=128, chunk_size=17)

    assert payload["schema_version"] == "account_export.v1"
    assert payload["generated_at"]
    assert len(payload["orders"]) == 205
    assert len(payload["loyalty_transactions"]) == 105
    assert payload["order_items"] == [
        {
            "line_id": "line-1",
            "sku": "PAO-01",
            "name": "Pão francês",
            "qty": "2.000",
            "unit_price_q": 100,
            "line_total_q": 200,
            "meta": {"customer_note": "bem assado"},
            "order_ref": first_order.ref,
        }
    ]
    assert payload["conversation_messages"][0]["conversation_id"] == conversation.pk
    assert payload["conversation_messages"][0]["text"] == message.text
    assert payload["conversation_messages"][0]["content"] == [
        {"type": "text", "text": "Prefiro retirar depois das 17h"}
    ]
    assert payload["favorites"][0]["sku"] == "PAO-01"
    assert payload["stock_alert_subscriptions"][0]["contact_phone"] == customer.phone
    assert payload["marketing_audience_members"][0]["reasons"] == ["consent"]
    assert payload["customer"]["metadata"] == {
        "preferences": "sem lactose",
        "fiscal_prefs": {"cpf_na_nota": True, "email_receipt": False},
    }
    assert counts["orders"] == payload["section_counts"]["orders"] == 205
    assert counts["loyalty_transactions"] == 105


def test_export_auth_records_exclude_credentials_and_secret_hashes():
    customer = _customer(suffix="02")
    user = get_user_model().objects.create_user(
        username="export-user",
        email=customer.email,
        password="raw-password-never-exported",
    )
    CustomerUser.objects.create(
        user=user,
        customer_id=customer.uuid,
        metadata={"refresh_token": "customer-user-secret"},
    )
    TrustedDevice.objects.create(
        subject_type="customer",
        subject_id=str(customer.uuid),
        token_hash="a" * 64,
        label="Celular da Ana",
        user_agent="Browser",
    )
    VerificationCode.objects.create(
        customer_id=customer.uuid,
        target_value=customer.phone,
        code_hash="b" * 64,
        status="verified",
    )

    payload, _counts = _decoded_export(customer)
    keys = set(_all_keys(payload))

    assert payload["auth_accounts"][0]["user__username"] == "export-user"
    assert payload["auth_trusted_devices"][0]["label"] == "Celular da Ana"
    assert payload["auth_verification_codes"][0]["status"] == "verified"
    assert not {
        "password",
        "token_hash",
        "code_hash",
        "pin_hash",
        "badge_hash",
        "credential_id",
        "public_key",
        "secret",
        "refresh_token",
    } & keys
    encoded = json.dumps(payload)
    assert "raw-password-never-exported" not in encoded
    assert "customer-user-secret" not in encoded
    assert "a" * 64 not in encoded
    assert "b" * 64 not in encoded


def test_export_rolls_to_disk_and_caller_owns_successful_spool():
    customer = _customer(suffix="03")

    artifact = account_export.build_account_export(customer, spool_max_size=1)

    assert artifact._rolled is True
    assert artifact.tell() == 0
    assert artifact.byte_count > 1
    assert artifact.closed is False
    artifact.close()
    assert artifact.closed is True


def test_export_closes_partial_spool_on_error(monkeypatch):
    customer = _customer(suffix="04")
    created = []
    real_spooled_file = tempfile.SpooledTemporaryFile

    def capture_spool(*args, **kwargs):
        spool = real_spooled_file(*args, **kwargs)
        created.append(spool)
        return spool

    def fail(_writer, _customer):
        raise RuntimeError("encoding failed")

    monkeypatch.setattr(account_export.tempfile, "SpooledTemporaryFile", capture_spool)
    monkeypatch.setattr(account_export, "_write_export", fail)

    with pytest.raises(RuntimeError, match="encoding failed"):
        account_export.build_account_export(customer)

    assert len(created) == 1
    assert created[0].closed is True


def test_export_never_claims_legacy_records_by_recycled_phone() -> None:
    current = _customer(suffix="05")
    previous = Customer.objects.create(ref="EXPORT-PREVIOUS", first_name="Outra pessoa")
    alien_order = Order.objects.create(
        ref="EXP-ALIEN-ORDER",
        channel_ref="web",
        handle_type="phone",
        handle_ref=current.phone,
        status="completed",
        data={"customer_ref": previous.ref, "customer": {"phone": current.phone}},
    )
    ownerless_order = Order.objects.create(
        ref="EXP-OWNERLESS-ORDER",
        channel_ref="web",
        handle_type="phone",
        handle_ref=current.phone,
        status="completed",
        data={"customer": {"phone": current.phone}},
    )
    VerificationCode.objects.create(
        customer_id=previous.uuid,
        target_value=current.phone,
        code_hash="f" * 64,
    )
    StockAlertSubscription.objects.create(
        sku="PAO-03",
        customer_ref=previous.ref,
        contact_phone=current.phone,
        target_key="g" * 64,
        evidence_hash="h" * 64,
    )

    payload, _counts = _decoded_export(current)

    refs = {row["ref"] for row in payload["orders"]}
    assert ownerless_order.ref not in refs
    assert alien_order.ref not in refs
    assert payload["auth_verification_codes"] == []
    assert payload["stock_alert_subscriptions"] == []


@pytest.mark.parametrize(
    "slot_ref,label",
    [("slot-09", "A partir das 09h"), ("14:00-14:30", "14:00 às 14:30")],
)
def test_export_labels_the_agreed_window_next_to_its_raw_ref(slot_ref, label) -> None:
    """O titular lê o export: "slot-09" é identificador interno. O ref fica
    (é o dado gravado) e o rótulo vai junto, pelas DUAS grades."""
    customer = _customer(suffix="77")
    Order.objects.create(
        ref="EXP-WINDOW",
        channel_ref="web",
        handle_type="phone",
        handle_ref=customer.phone,
        status="completed",
        data={"customer_ref": customer.ref, "delivery_date": "2026-09-20", "delivery_time_slot": slot_ref},
        total_q=1000,
    )

    payload, _counts = _decoded_export(customer)

    (row,) = payload["orders"]
    assert row["data"]["delivery_time_slot"] == slot_ref
    assert row["data"]["delivery_time_slot_label"] == label


def test_export_without_a_window_has_no_label() -> None:
    customer = _customer(suffix="78")
    Order.objects.create(
        ref="EXP-NO-WINDOW", channel_ref="web", handle_type="phone", handle_ref=customer.phone,
        status="completed", data={"customer_ref": customer.ref}, total_q=1000,
    )

    payload, _counts = _decoded_export(customer)

    (row,) = payload["orders"]
    assert "delivery_time_slot_label" not in row["data"]
