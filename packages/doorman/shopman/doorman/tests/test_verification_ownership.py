"""OTP ownership is revalidated after the canonical Customer lock."""

from __future__ import annotations

from io import StringIO
from unittest.mock import Mock

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.utils import timezone
from shopman.doorman.error_codes import ErrorCode
from shopman.doorman.models import VerificationCode
from shopman.doorman.models.verification_code import generate_raw_code
from shopman.doorman.services.verification import AuthService
from shopman.guestman.adapters.auth import CustomerResolver
from shopman.guestman.models import ContactPoint, Customer


def _replace_login_target(customer: Customer, kind: str, value: str) -> None:
    """Apply the winning contact change while the Customer row is locked."""
    if kind == "phone":
        from shopman.shop.services.account import _set_primary_phone

        _set_primary_phone(customer, value)
        return

    ContactPoint.objects.filter(
        customer=customer,
        type=ContactPoint.Type.EMAIL,
    ).delete()
    customer.email = value
    customer.save(update_fields=["email", "updated_at"])


def _move_target_when_auth_locks(
    monkeypatch,
    *,
    kind: str,
    replacement: str,
) -> None:
    """Deterministically model a contact change winning before auth's lock."""

    def move_then_return_current(resolver, customer_uuid):
        customer = Customer.objects.select_for_update().get(
            uuid=customer_uuid,
            is_active=True,
        )
        _replace_login_target(customer, kind, replacement)
        customer.refresh_from_db()
        return resolver._to_info(customer)

    monkeypatch.setattr(CustomerResolver, "lock_active_by_uuid", move_then_return_current)


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("kind", "replacement", "delivery_method"),
    (
        ("phone", "+5543999990001", VerificationCode.DeliveryMethod.SMS),
        ("email", "new-owner@example.com", VerificationCode.DeliveryMethod.EMAIL),
    ),
)
def test_request_code_does_not_send_to_target_removed_before_customer_lock(
    customer,
    monkeypatch,
    kind,
    replacement,
    delivery_method,
):
    old_target = customer.phone if kind == "phone" else customer.email
    sender = Mock()
    sender.send_code.return_value = True
    _move_target_when_auth_locks(
        monkeypatch,
        kind=kind,
        replacement=replacement,
    )

    result = AuthService.request_code(
        old_target,
        delivery_method=delivery_method,
        sender=sender,
    )

    assert result.success is False
    assert result.error_code == ErrorCode.ACCOUNT_INACTIVE
    sender.send_code.assert_not_called()
    assert not VerificationCode.objects.filter(target_value=old_target).exists()


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("kind", "replacement"),
    (
        ("phone", "+5543999990002"),
        ("email", "changed-before-verify@example.com"),
    ),
)
def test_verify_rejects_code_when_target_was_removed_before_customer_lock(
    customer,
    monkeypatch,
    kind,
    replacement,
):
    old_target = customer.phone if kind == "phone" else customer.email
    raw_code, digest = generate_raw_code()
    code = VerificationCode.objects.create(
        code_hash=digest,
        target_value=old_target,
        purpose=VerificationCode.Purpose.LOGIN,
        delivery_method=(
            VerificationCode.DeliveryMethod.SMS
            if kind == "phone"
            else VerificationCode.DeliveryMethod.EMAIL
        ),
        customer_id=customer.uuid,
    )
    code.mark_sent()
    _move_target_when_auth_locks(
        monkeypatch,
        kind=kind,
        replacement=replacement,
    )

    result = AuthService.verify_for_login(old_target, raw_code)

    assert result.success is False
    assert result.error_code == ErrorCode.CODE_EXPIRED
    code.refresh_from_db()
    assert code.status == VerificationCode.Status.SENT


@pytest.mark.django_db
def test_verify_rejects_code_bound_to_a_different_customer(customer, other_customer):
    raw_code, digest = generate_raw_code()
    code = VerificationCode.objects.create(
        code_hash=digest,
        target_value=customer.phone,
        purpose=VerificationCode.Purpose.LOGIN,
        delivery_method=VerificationCode.DeliveryMethod.SMS,
        customer_id=other_customer.uuid,
        status=VerificationCode.Status.SENT,
    )

    result = AuthService.verify_for_login(customer.phone, raw_code)

    assert result.success is False
    assert result.error_code == ErrorCode.CODE_EXPIRED
    code.refresh_from_db()
    assert code.status == VerificationCode.Status.SENT


@pytest.mark.django_db
def test_otp_reconciliation_cannot_accept_a_code_after_contact_ownership_changes(
    customer,
):
    old_phone = customer.phone
    code = VerificationCode.objects.create(
        target_value=old_phone,
        purpose=VerificationCode.Purpose.LOGIN,
        customer_id=customer.uuid,
        status=VerificationCode.Status.PENDING,
        delivery_started_at=timezone.now(),
    )
    _replace_login_target(customer, "phone", "+5543999990012")

    with pytest.raises(CommandError, match="contato mudou"):
        call_command(
            "reconcile_otp_delivery_privacy",
            code_id=str(code.pk),
            outcome="accepted",
            evidence_ref="provider-ticket/OTP-OWNERSHIP-001",
            stdout=StringIO(),
        )

    code.refresh_from_db()
    assert code.status == VerificationCode.Status.PENDING
    assert code.delivery_reconciled_at is None

    call_command(
        "reconcile_otp_delivery_privacy",
        code_id=str(code.pk),
        outcome="rejected",
        evidence_ref="provider-ticket/OTP-OWNERSHIP-002",
        stdout=StringIO(),
    )
    code.refresh_from_db()
    assert code.status == VerificationCode.Status.FAILED
