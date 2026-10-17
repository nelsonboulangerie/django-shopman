from __future__ import annotations

import logging
import uuid
from unittest.mock import Mock

import pytest
from django.db import IntegrityError
from django.http import HttpResponse
from django.test import RequestFactory, override_settings
from shopman.doorman.adapter import DefaultAuthAdapter
from shopman.doorman.error_codes import ErrorCode
from shopman.doorman.models import TrustedDevice, VerificationCode
from shopman.doorman.models.verification_code import generate_raw_code
from shopman.doorman.protocols.identity import IdentityConflict, IdentityHandle, IdentityView
from shopman.doorman.services.device_trust import DeviceTrustService
from shopman.doorman.services.verification import AuthService
from shopman.guestman.adapters.auth import IdentityResolver, ManychatIdentityBridge
from shopman.guestman.contrib.identifiers.models import CustomerIdentifier, IdentifierType
from shopman.guestman.models import ContactPoint, Customer
from shopman.guestman.services import identity as identity_service

pytestmark = pytest.mark.django_db


class ContractFakeIdentityResolver:
    identity: IdentityView | None = None
    create_calls = 0
    bind_calls = 0
    bind_proofs: list[str] = []
    conflict = False

    def resolve(self, kind, value, *, purpose="login"):
        if self.conflict:
            raise IdentityConflict("fake_ambiguous_ownership")
        if self.identity is None:
            return None
        matches = tuple(
            handle
            for handle in self.identity.handles
            if handle.value == value
            and (handle.kind == kind or {handle.kind, kind} <= {"phone", "whatsapp"})
        )
        if not matches:
            return None
        return IdentityView(
            self.identity.subject_id,
            self.identity.name,
            matches,
            self.identity.is_active,
        )

    def get(self, subject_id, *, purpose):
        return self.identity if self.identity and self.identity.subject_id == subject_id else None

    def lock_active(self, subject_id, *, purpose):
        identity = self.get(subject_id, purpose=purpose)
        return identity if identity and identity.is_active else None

    def create(self, kind, value):
        type(self).create_calls += 1
        raise AssertionError("secondary handle must not auto-create")

    def bind_verified_handle(self, subject_id, kind, value, *, proof):
        type(self).bind_calls += 1
        type(self).bind_proofs.append(proof)
        return self.identity


_CONTRACT_FAKE_PATH = f"{__name__}.ContractFakeIdentityResolver"


def test_identity_view_primary_is_explicit_not_tuple_order():
    secondary = IdentityHandle("email", "secondary@example.com", True, False)
    primary = IdentityHandle("email", "primary@example.com", True, True)
    view = IdentityView(uuid.uuid4(), "Ana", (secondary, primary), True)

    assert view.handle("email") == primary


def test_identity_view_repr_redacts_name_and_handles():
    sentinel_name = "Sensitive Person"
    sentinel_handle = "private@example.com"
    view = IdentityView(
        uuid.uuid4(),
        sentinel_name,
        (IdentityHandle("email", sentinel_handle, True, True),),
        True,
    )

    rendered = repr(view)

    assert sentinel_name not in rendered
    assert sentinel_handle not in rendered


@override_settings(DOORMAN={"IDENTITY_RESOLVER_CLASS": _CONTRACT_FAKE_PATH})
def test_doorman_contract_fake_logs_in_secondary_without_promoting_or_creating():
    subject_id = uuid.uuid4()
    primary = IdentityHandle("phone", "+5543999990120", True, True)
    secondary = IdentityHandle("phone", "+5543999990121", True, False)
    ContractFakeIdentityResolver.identity = IdentityView(
        subject_id,
        "Ana",
        (secondary, primary),
        True,
    )
    ContractFakeIdentityResolver.create_calls = 0
    ContractFakeIdentityResolver.bind_calls = 0
    ContractFakeIdentityResolver.bind_proofs = []
    ContractFakeIdentityResolver.conflict = False
    raw_code, digest = generate_raw_code()
    VerificationCode.objects.create(
        code_hash=digest,
        target_value=secondary.value,
        purpose=VerificationCode.Purpose.LOGIN,
        status=VerificationCode.Status.SENT,
    )

    result = AuthService.verify_for_login(secondary.value, raw_code)

    assert result.success is True
    assert result.customer.handle("phone").value == primary.value
    assert ContractFakeIdentityResolver.create_calls == 0
    assert ContractFakeIdentityResolver.bind_calls == 1
    assert ContractFakeIdentityResolver.bind_proofs == ["whatsapp"]
    assert primary.primary is True
    assert secondary.primary is False


@override_settings(DOORMAN={"IDENTITY_RESOLVER_CLASS": _CONTRACT_FAKE_PATH})
def test_doorman_contract_fake_conflict_fails_closed_without_create():
    ContractFakeIdentityResolver.identity = None
    ContractFakeIdentityResolver.create_calls = 0
    ContractFakeIdentityResolver.bind_calls = 0
    ContractFakeIdentityResolver.conflict = True

    result = AuthService.request_code("+5543999990122")

    assert result.success is False
    assert result.error_code == ErrorCode.IDENTITY_CONFLICT
    assert ContractFakeIdentityResolver.create_calls == 0
    ContractFakeIdentityResolver.conflict = False


@pytest.mark.parametrize("value", ["+5543999990198", "private@example.com"])
def test_identity_contract_repr_redacts_handle_value(value):
    handle = IdentityHandle("email" if "@" in value else "phone", value, True, True)
    view = IdentityView(uuid.uuid4(), "Ana", (handle,), True)

    assert value not in repr(handle)
    assert value not in repr(view)


def test_resolve_secondary_handle_preserves_existing_primary(customer):
    customer.contact_points.all().delete()
    primary = ContactPoint.objects.create(
        customer=customer,
        type=ContactPoint.Type.WHATSAPP,
        value_normalized=customer.phone,
        is_primary=True,
        is_verified=True,
    )
    secondary = ContactPoint.objects.create(
        customer=customer,
        type=ContactPoint.Type.WHATSAPP,
        value_normalized="+5543999990101",
        is_primary=False,
        is_verified=True,
    )

    resolved = IdentityResolver().resolve("phone", secondary.value_normalized)

    assert resolved.subject_id == customer.uuid
    assert {handle.value for handle in resolved.handles} == {secondary.value_normalized}
    assert resolved.handle("whatsapp").value == secondary.value_normalized

    raw_code, digest = generate_raw_code()
    VerificationCode.objects.create(
        code_hash=digest,
        target_value=secondary.value_normalized,
        purpose=VerificationCode.Purpose.LOGIN,
        delivery_method=VerificationCode.DeliveryMethod.SMS,
        customer_id=customer.uuid,
        status=VerificationCode.Status.SENT,
    )
    result = AuthService.verify_for_login(secondary.value_normalized, raw_code)

    assert result.success is True
    customer.refresh_from_db()
    primary.refresh_from_db()
    secondary.refresh_from_db()
    assert customer.phone == primary.value_normalized
    assert primary.is_primary is True
    assert secondary.is_primary is False
    claimed_phone = ContactPoint.objects.get(
        customer=customer,
        type=ContactPoint.Type.PHONE,
        value_normalized=secondary.value_normalized,
    )
    assert claimed_phone.is_primary is False


def test_phone_resolution_materializes_identifier_only_whatsapp_handle(customer):
    customer.contact_points.all().delete()
    customer.phone = ""
    customer.save(update_fields=["phone"])
    value = "+5543999990105"
    CustomerIdentifier.objects.create(
        customer=customer,
        identifier_type=IdentifierType.WHATSAPP,
        identifier_value=value,
        is_primary=True,
    )

    resolved = IdentityResolver().resolve("phone", value)

    assert resolved.subject_id == customer.uuid
    assert resolved.handle("whatsapp").value == value


def test_access_link_manychat_resolution_includes_persisted_phone(customer):
    CustomerIdentifier.objects.create(
        customer=customer,
        identifier_type=IdentifierType.MANYCHAT,
        identifier_value="mc-identity-01",
    )

    resolved = IdentityResolver().resolve(
        "manychat",
        "mc-identity-01",
        purpose="access_link",
    )

    assert resolved.handle("manychat").value == "mc-identity-01"
    assert resolved.handle("phone") or resolved.handle("whatsapp")


@pytest.mark.parametrize("entrypoint", ["access_link", "subscriber"])
@pytest.mark.parametrize("conflict_type", ["ownership", "integrity"])
def test_manychat_bridge_translates_write_races_without_pii(
    customer,
    monkeypatch,
    caplog,
    entrypoint,
    conflict_type,
):
    from shopman.guestman.contrib.manychat.service import ManychatService

    sentinel = "+5543999990999-private"
    conflict = (
        identity_service.ContactPointOwnershipConflict(sentinel)
        if conflict_type == "ownership"
        else IntegrityError(sentinel)
    )
    bridge = ManychatIdentityBridge()
    caplog.set_level(logging.DEBUG)

    if entrypoint == "access_link":
        monkeypatch.setattr(ManychatService, "sync_customer", Mock(side_effect=conflict))

        def invoke():
            return bridge.upsert_access_link_subject(
                customer.uuid,
                {"id": "subscriber-private", "whatsapp_id": sentinel},
            )

    else:
        monkeypatch.setattr(ManychatService, "sync_subscriber", Mock(side_effect=conflict))

        def invoke():
            return bridge.upsert_subscriber(
                {"id": "subscriber-private", "whatsapp_id": sentinel}
            )

    with pytest.raises(IdentityConflict, match="manychat_identity_conflict") as caught:
        invoke()

    assert caught.value.__cause__ is None
    assert caught.value.__suppress_context__ is True
    assert sentinel not in caplog.text


def test_cache_primary_wins_over_secondary_identifier_independent_of_order(customer):
    primary = "+5543999990106"
    secondary = "+5543999990107"
    customer.contact_points.all().delete()
    customer.identifiers.all().delete()
    Customer.objects.filter(pk=customer.pk).update(phone=primary)
    customer.refresh_from_db()
    CustomerIdentifier.objects.create(
        customer=customer,
        identifier_type=IdentifierType.PHONE,
        identifier_value=secondary,
        is_primary=False,
    )

    resolved = IdentityResolver().get(customer.uuid, purpose="session")

    assert tuple(
        handle.value for handle in resolved.handles if handle.kind in {"phone", "whatsapp"}
    ) == (primary, secondary)
    assert resolved.handle("phone").value == primary


@pytest.mark.parametrize("cache_source", ["secondary", "unrelated"])
def test_contact_point_primary_outranks_stale_customer_cache(customer, cache_source):
    customer.contact_points.all().delete()
    primary = "+5543999990109"
    secondary = "+5543999990110"
    ContactPoint.objects.create(
        customer=customer,
        type=ContactPoint.Type.PHONE,
        value_normalized=primary,
        is_primary=True,
    )
    ContactPoint.objects.create(
        customer=customer,
        type=ContactPoint.Type.PHONE,
        value_normalized=secondary,
        is_primary=False,
    )
    stale = secondary if cache_source == "secondary" else "+5543999990111"
    Customer.objects.filter(pk=customer.pk).update(phone=stale)
    customer.refresh_from_db()

    resolved = IdentityResolver().get(customer.uuid, purpose="session")

    assert resolved.handle("phone").value == primary
    assert sum(handle.primary for handle in resolved.handles if handle.kind == "phone") == 1


def test_login_resolution_exposes_only_requested_value(customer):
    requested = "+5543999990112"
    other = "+5543999990113"
    ContactPoint.objects.create(
        customer=customer,
        type=ContactPoint.Type.WHATSAPP,
        value_normalized=requested,
        is_primary=False,
    )
    ContactPoint.objects.create(
        customer=customer,
        type=ContactPoint.Type.WHATSAPP,
        value_normalized=other,
        is_primary=False,
    )

    resolved = IdentityResolver().resolve("phone", requested, purpose="login")

    assert {handle.value for handle in resolved.handles} == {requested}


def test_identifier_first_cross_table_conflict_fails_closed(customer, other_customer):
    value = "+5543999990102"
    CustomerIdentifier.objects.create(
        customer=customer,
        identifier_type=IdentifierType.PHONE,
        identifier_value=value,
    )
    ContactPoint.objects.create(
        customer=other_customer,
        type=ContactPoint.Type.WHATSAPP,
        value_normalized=value,
        is_verified=True,
    )

    with pytest.raises(IdentityConflict, match="multiple_subjects"):
        IdentityResolver().resolve("phone", value)

    assert Customer.objects.filter(is_active=True).count() == 2


@pytest.mark.parametrize("operation", ["request", "verify"])
def test_auth_service_returns_typed_identity_conflict_without_creating_third_customer(
    customer,
    other_customer,
    operation,
):
    value = "+5543999990104"
    CustomerIdentifier.objects.create(
        customer=customer,
        identifier_type=IdentifierType.PHONE,
        identifier_value=value,
    )
    ContactPoint.objects.create(
        customer=other_customer,
        type=ContactPoint.Type.WHATSAPP,
        value_normalized=value,
        is_verified=True,
    )
    customer_count = Customer.objects.count()

    if operation == "request":
        result = AuthService.request_code(value)
    else:
        raw_code, digest = generate_raw_code()
        VerificationCode.objects.create(
            code_hash=digest,
            target_value=value,
            purpose=VerificationCode.Purpose.LOGIN,
            status=VerificationCode.Status.SENT,
        )
        result = AuthService.verify_for_login(value, raw_code)

    assert result.success is False
    assert result.error_code == ErrorCode.IDENTITY_CONFLICT
    assert Customer.objects.count() == customer_count


@pytest.mark.parametrize("operation", ["request", "verify"])
def test_inactive_handle_owner_fails_closed_without_creating_customer(customer, operation):
    value = customer.phone
    customer.is_active = False
    customer.save(update_fields=["is_active"])
    customer_count = Customer.objects.count()

    if operation == "request":
        result = AuthService.request_code(value)
    else:
        raw_code, digest = generate_raw_code()
        VerificationCode.objects.create(
            code_hash=digest,
            target_value=value,
            purpose=VerificationCode.Purpose.LOGIN,
            status=VerificationCode.Status.SENT,
        )
        result = AuthService.verify_for_login(value, raw_code)

    assert result.success is False
    assert result.error_code == ErrorCode.ACCOUNT_INACTIVE
    assert Customer.objects.count() == customer_count


def test_verify_rolls_back_real_create_when_bind_conflicts(monkeypatch):
    value = "+5543999990108"
    raw_code, digest = generate_raw_code()
    VerificationCode.objects.create(
        code_hash=digest,
        target_value=value,
        purpose=VerificationCode.Purpose.LOGIN,
        status=VerificationCode.Status.SENT,
    )
    customer_count = Customer.objects.count()

    def conflict(_adapter, identity, handle, *, proof):
        assert Customer.objects.filter(uuid=identity.subject_id).exists()
        assert proof == VerificationCode.DeliveryMethod.WHATSAPP
        raise IdentityConflict("verified_handle_conflict")

    monkeypatch.setattr(DefaultAuthAdapter, "bind_verified_handle", conflict)

    result = AuthService.verify_for_login(value, raw_code)

    assert result.success is False
    assert result.error_code == ErrorCode.IDENTITY_CONFLICT
    assert Customer.objects.count() == customer_count
    assert not ContactPoint.objects.filter(value_normalized=value).exists()
    assert not CustomerIdentifier.objects.filter(identifier_value=value).exists()


@pytest.mark.parametrize("operation", ["create", "bind"])
def test_unknown_identity_kind_is_rejected_without_writes(customer, operation):
    resolver = IdentityResolver()
    before_customers = Customer.objects.count()
    before_contacts = ContactPoint.objects.count()
    before_identifiers = CustomerIdentifier.objects.count()

    with pytest.raises(IdentityConflict, match="unsupported_identity_kind"):
        if operation == "create":
            resolver.create("manychat", "subscriber-should-not-be-a-phone")
        else:
            resolver.bind_verified_handle(
                customer.uuid,
                "manychat",
                "subscriber-should-not-be-a-phone",
                proof="whatsapp",
            )

    assert Customer.objects.count() == before_customers
    assert ContactPoint.objects.count() == before_contacts
    assert CustomerIdentifier.objects.count() == before_identifiers


def test_bind_verified_secondary_rolls_back_on_conflict_and_never_promotes(customer, other_customer):
    primary = ContactPoint.objects.create(
        customer=customer,
        type=ContactPoint.Type.WHATSAPP,
        value_normalized=customer.phone,
        is_primary=True,
        is_verified=True,
    )
    contested = "+5543999990103"
    CustomerIdentifier.objects.create(
        customer=other_customer,
        identifier_type=IdentifierType.WHATSAPP,
        identifier_value=contested,
    )

    with pytest.raises(IdentityConflict):
        IdentityResolver().bind_verified_handle(
            customer.uuid,
            "phone",
            contested,
            proof="whatsapp",
        )

    primary.refresh_from_db()
    assert primary.is_primary is True
    assert not ContactPoint.objects.filter(customer=customer, value_normalized=contested).exists()
    assert not CustomerIdentifier.objects.filter(customer=customer, identifier_value=contested).exists()


@pytest.mark.parametrize(
    ("kind", "proof", "expected_method"),
    [
        ("phone", "sms", ContactPoint.VerificationMethod.OTP_SMS),
        ("phone", "whatsapp", ContactPoint.VerificationMethod.OTP_WHATSAPP),
        ("whatsapp", "whatsapp", ContactPoint.VerificationMethod.OTP_WHATSAPP),
        ("email", "email", ContactPoint.VerificationMethod.OTP_EMAIL),
    ],
)
def test_verified_bind_persists_real_channel_proof(customer, kind, proof, expected_method):
    value = "otp-channel@example.com" if kind == "email" else "+5543999990130"

    IdentityResolver().bind_verified_handle(customer.uuid, kind, value, proof=proof)

    contact = ContactPoint.objects.get(
        customer=customer,
        type={
            "phone": ContactPoint.Type.PHONE,
            "whatsapp": ContactPoint.Type.WHATSAPP,
            "email": ContactPoint.Type.EMAIL,
        }[kind],
        value_normalized=value,
    )
    assert contact.is_verified is True
    assert contact.verification_method == expected_method
    assert contact.verified_at is not None


def test_email_otp_binding_never_claims_email_link_proof(customer):
    value = "otp-proof@example.com"

    IdentityResolver().bind_verified_handle(
        customer.uuid,
        "email",
        value,
        proof="email",
    )

    contact = ContactPoint.objects.get(
        customer=customer,
        type=ContactPoint.Type.EMAIL,
        value_normalized=value,
    )
    assert contact.verification_method == ContactPoint.VerificationMethod.OTP_EMAIL
    assert contact.verification_method != ContactPoint.VerificationMethod.EMAIL_LINK


def test_whatsapp_writer_claims_canonical_phone_and_blocks_phone_bind(
    customer,
    other_customer,
):
    value = "+5543999990131"
    identity_service.ensure_contact_point(
        other_customer,
        type=ContactPoint.Type.WHATSAPP,
        value_normalized=value,
    )

    with pytest.raises(IdentityConflict, match="another_subject"):
        IdentityResolver().bind_verified_handle(
            customer.uuid,
            "phone",
            value,
            proof="sms",
        )

    canonical = ContactPoint.objects.get(
        type=ContactPoint.Type.PHONE,
        value_normalized=value,
    )
    assert canonical.customer_id == other_customer.pk
    assert not ContactPoint.objects.filter(customer=customer, value_normalized=value).exists()


@pytest.mark.parametrize("foreign_type", ["display", "station"])
def test_revoke_device_does_not_revoke_token_owned_by_another_subject_type(foreign_type):
    foreign_id = "surface-01"
    device, raw_token = TrustedDevice.create_for(foreign_type, foreign_id)
    request = RequestFactory().post("/logout/")
    request.COOKIES[DeviceTrustService.cookie_name_for("customer", uuid.uuid4())] = raw_token
    response = HttpResponse()

    DeviceTrustService.revoke_device(
        request,
        response,
        subject_type="customer",
        subject_id=uuid.uuid4(),
    )

    device.refresh_from_db()
    assert device.is_active is True
    assert device.last_used_at is None


def test_revoke_device_only_revokes_same_customer_subject():
    owner = uuid.uuid4()
    other = uuid.uuid4()
    device, raw_token = TrustedDevice.create_for("customer", owner)
    request = RequestFactory().post("/logout/")
    request.COOKIES[DeviceTrustService.cookie_name_for("customer", other)] = raw_token

    DeviceTrustService.revoke_device(
        request,
        HttpResponse(),
        subject_type="customer",
        subject_id=other,
    )

    device.refresh_from_db()
    assert device.is_active is True
    assert device.last_used_at is None


@pytest.mark.parametrize("handle", ["+5543999990199", "private@example.com"])
def test_verification_failure_logs_no_raw_handle_or_code(caplog, handle):

    class FailingSender:
        raw_code = ""

        def send_code(self, target, code, method):
            self.raw_code = code
            raise RuntimeError(f"provider rejected {target} with code {code}")

    sender = FailingSender()
    with caplog.at_level(logging.INFO):
        result = AuthService.request_code(handle, sender=sender)

    assert result.success is False
    rendered = caplog.text
    assert handle not in rendered
    assert sender.raw_code
    assert sender.raw_code not in rendered
    assert "@" not in rendered
