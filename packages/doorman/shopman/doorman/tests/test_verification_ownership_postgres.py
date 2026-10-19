"""Real row-lock proof for OTP versus a concurrent contact change."""

from __future__ import annotations

import uuid
from concurrent.futures import ThreadPoolExecutor
from io import StringIO
from threading import Barrier, Event
from time import monotonic

import pytest
from django.apps import apps
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import close_old_connections, connection, connections, transaction
from django.test import override_settings
from django.utils import timezone
from shopman.doorman.error_codes import ErrorCode
from shopman.doorman.models import VerificationCode
from shopman.doorman.models.verification_code import generate_raw_code
from shopman.doorman.protocols.identity import IdentityConflict
from shopman.doorman.services.verification import AuthService
from shopman.guestman.adapters.auth import IdentityResolver
from shopman.guestman.contrib.identifiers.models import CustomerIdentifier, IdentifierType
from shopman.guestman.contrib.manychat.resolver import ManychatSubscriberResolver
from shopman.guestman.models import ContactPoint, Customer
from shopman.guestman.services import customer as customer_service

if not apps.is_installed("shopman.shop"):
    pytest.skip(
        "OTP x exclusão é integração monolítica registrada no runtime gate",
        allow_module_level=True,
    )

from shopman.shop.adapters.otp_manychat import ManychatOTPSender
from shopman.storefront.services import account_privacy

requires_postgres = pytest.mark.skipif(
    connection.vendor != "postgresql",
    reason="Requires independent PostgreSQL connections and row locks",
)

pytestmark = [pytest.mark.django_db(transaction=True), requires_postgres]


class Worker:
    def __init__(self, command):
        self.command = command
        self.started = Event()
        self.pid = None

    def __call__(self):
        close_old_connections()
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_backend_pid()")
                self.pid = cursor.fetchone()[0]
                cursor.execute("SET lock_timeout = '15s'")
            self.started.set()
            return self.command()
        finally:
            connections.close_all()


class RecordingSender:
    def __init__(self):
        self.calls = []

    def send_code(self, target, code, method):
        self.calls.append((target, code, method))
        return True


def _assert_database_wait(worker: Worker) -> None:
    assert worker.started.wait(10)
    deadline = monotonic() + 10
    while monotonic() < deadline:
        with connection.cursor() as cursor:
            cursor.execute("SELECT cardinality(pg_blocking_pids(%s))", [worker.pid])
            if cursor.fetchone()[0] > 0:
                return
        Event().wait(0.01)
    pytest.fail(f"Connection {worker.pid} did not wait for the Customer lock")


def _change_phone_while_holding_customer(
    customer_pk,
    replacement,
    changed: Event,
    release: Event,
):
    from shopman.shop.services.account import _set_primary_phone

    with transaction.atomic():
        customer = Customer.objects.select_for_update().get(pk=customer_pk)
        _set_primary_phone(customer, replacement, proof="sms")
        changed.set()
        assert release.wait(10)


@pytest.mark.parametrize(
    ("first_kind", "second_kind"),
    [("phone", "phone"), ("phone", "whatsapp")],
)
def test_concurrent_verified_bind_has_one_owner_and_one_typed_conflict(
    customer,
    other_customer,
    monkeypatch,
    first_kind,
    second_kind,
):
    value = "+5543999990181"
    both_resolved_absent = Barrier(2)
    original_resolve = IdentityResolver.resolve

    def synchronize_after_absent_resolve(resolver, kind, candidate, *, purpose="login"):
        result = original_resolve(resolver, kind, candidate, purpose=purpose)
        if candidate == value and result is None:
            both_resolved_absent.wait(timeout=10)
        return result

    monkeypatch.setattr(IdentityResolver, "resolve", synchronize_after_absent_resolve)

    def bind(subject_id, kind):
        try:
            return IdentityResolver().bind_verified_handle(
                subject_id,
                kind,
                value,
                proof="whatsapp",
            )
        except IdentityConflict as exc:
            return exc

    first = Worker(lambda: bind(customer.uuid, first_kind))
    second = Worker(lambda: bind(other_customer.uuid, second_kind))
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(first), pool.submit(second)]
        results = [future.result(20) for future in futures]

    views = [result for result in results if not isinstance(result, IdentityConflict)]
    conflicts = [result for result in results if isinstance(result, IdentityConflict)]
    assert len(views) == 1
    assert len(conflicts) == 1
    assert ContactPoint.objects.filter(
        type=ContactPoint.Type.PHONE,
        value_normalized=value,
    ).count() == 1
    assert IdentityResolver().resolve("phone", value).subject_id == views[0].subject_id


def test_concurrent_bridge_bind_and_shop_phone_writer_share_canonical_claim(
    customer,
    other_customer,
    monkeypatch,
):
    from shopman.shop.services import account as account_service

    value = "+5543999990183"
    both_checked_absent = Barrier(2)
    original_resolve = IdentityResolver.resolve
    original_owned = account_service._phone_belongs_to_someone_else

    def bridge_absent_then_wait(resolver, kind, candidate, *, purpose="login"):
        result = original_resolve(resolver, kind, candidate, purpose=purpose)
        if candidate == value and result is None:
            both_checked_absent.wait(timeout=10)
        return result

    def shop_absent_then_wait(shop_customer, candidate):
        result = original_owned(shop_customer, candidate)
        if candidate == value and result is False:
            both_checked_absent.wait(timeout=10)
        return result

    monkeypatch.setattr(IdentityResolver, "resolve", bridge_absent_then_wait)
    monkeypatch.setattr(
        account_service,
        "_phone_belongs_to_someone_else",
        shop_absent_then_wait,
    )

    def bridge_write():
        try:
            return IdentityResolver().bind_verified_handle(
                customer.uuid,
                "phone",
                value,
                proof="sms",
            )
        except IdentityConflict as exc:
            return exc

    def shop_write():
        try:
            account_service._set_primary_phone(other_customer, value, proof="sms")
            return other_customer.uuid
        except account_service.ContactAlreadyTaken as exc:
            return exc

    workers = [Worker(bridge_write), Worker(shop_write)]
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(worker) for worker in workers]
        results = [future.result(20) for future in futures]

    failures = [
        result
        for result in results
        if isinstance(result, (IdentityConflict, account_service.ContactAlreadyTaken))
    ]
    assert len(failures) == 1
    canonical = ContactPoint.objects.get(
        type=ContactPoint.Type.PHONE,
        value_normalized=value,
    )
    owners = set(
        ContactPoint.objects.filter(
            type__in=[ContactPoint.Type.PHONE, ContactPoint.Type.WHATSAPP],
            value_normalized=value,
        ).values_list("customer_id", flat=True)
    )
    assert owners == {canonical.customer_id}
    assert not ContactPoint.objects.filter(
        value_normalized=value,
    ).exclude(customer_id=canonical.customer_id).exists()


@pytest.mark.parametrize("kind", ["phone", "whatsapp", "email"])
def test_concurrent_identity_create_has_one_subject_and_one_typed_conflict(
    monkeypatch,
    kind,
):
    value = "claim@example.com" if kind == "email" else "+5543999990182"
    both_creating = Barrier(2)
    original_create = customer_service.create

    def synchronized_create(*args, **kwargs):
        both_creating.wait(timeout=10)
        return original_create(*args, **kwargs)

    monkeypatch.setattr(customer_service, "create", synchronized_create)

    def create():
        try:
            return IdentityResolver().create(kind, value)
        except IdentityConflict as exc:
            return exc

    workers = [Worker(create), Worker(create)]
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(worker) for worker in workers]
        results = [future.result(20) for future in futures]

    views = [result for result in results if not isinstance(result, IdentityConflict)]
    conflicts = [result for result in results if isinstance(result, IdentityConflict)]
    assert len(views) == 1
    assert len(conflicts) == 1
    if kind == "email":
        assert Customer.objects.filter(email=value).count() == 1
        contact_kind = ContactPoint.Type.EMAIL
    elif kind == "phone":
        assert Customer.objects.filter(phone=value).count() == 1
        contact_kind = ContactPoint.Type.PHONE
    else:
        assert Customer.objects.filter(phone=value).count() == 1
        contact_kind = ContactPoint.Type.WHATSAPP
    assert ContactPoint.objects.filter(
        type=contact_kind,
        value_normalized=value,
    ).count() == 1


@pytest.mark.parametrize("operation", ("request", "verify"))
def test_contact_change_wins_before_otp_customer_lock(
    customer,
    monkeypatch,
    operation,
):
    old_phone = customer.phone
    replacement = "+5543999990010" if operation == "request" else "+5543999990011"
    raw_code = None
    code = None
    sender = RecordingSender()
    if operation == "verify":
        raw_code, digest = generate_raw_code()
        code = VerificationCode.objects.create(
            code_hash=digest,
            target_value=old_phone,
            purpose=VerificationCode.Purpose.LOGIN,
            delivery_method=VerificationCode.DeliveryMethod.SMS,
            customer_id=customer.uuid,
            status=VerificationCode.Status.SENT,
        )

    lock_attempted = Event()
    original_lock = IdentityResolver.lock_active

    def observe_lock_attempt(resolver, customer_uuid, *, purpose):
        lock_attempted.set()
        return original_lock(resolver, customer_uuid, purpose=purpose)

    monkeypatch.setattr(IdentityResolver, "lock_active", observe_lock_attempt)

    changed, release = Event(), Event()
    change = Worker(
        lambda: _change_phone_while_holding_customer(
            customer.pk,
            replacement,
            changed,
            release,
        )
    )
    authenticate = Worker(
        lambda: (
            AuthService.request_code(
                old_phone,
                delivery_method=VerificationCode.DeliveryMethod.SMS,
                sender=sender,
            )
            if operation == "request"
            else AuthService.verify_for_login(old_phone, raw_code)
        )
    )

    with ThreadPoolExecutor(max_workers=2) as pool:
        changed_future = pool.submit(change)
        try:
            assert changed.wait(10)
            auth_future = pool.submit(authenticate)
            assert lock_attempted.wait(10)
            _assert_database_wait(authenticate)
        finally:
            release.set()
        assert changed_future.result(20) is None
        result = auth_future.result(20)

    assert result.success is False
    expected = ErrorCode.ACCOUNT_INACTIVE if operation == "request" else ErrorCode.CODE_EXPIRED
    assert result.error_code == expected
    assert sender.calls == []
    customer.refresh_from_db()
    assert customer.phone == replacement
    assert not ContactPoint.objects.filter(
        customer=customer,
        type__in=[ContactPoint.Type.PHONE, ContactPoint.Type.WHATSAPP],
        value_normalized=old_phone,
    ).exists()
    if code is not None:
        code.refresh_from_db()
        assert code.status == VerificationCode.Status.SENT
    else:
        assert not VerificationCode.objects.filter(target_value=old_phone).exists()


_MANYCHAT_OTP_DOORMAN = {
    "IDENTITY_RESOLVER_CLASS": "shopman.guestman.adapters.auth.IdentityResolver",
    "DELIVERY_CHAIN": ["whatsapp"],
    "DELIVERY_SENDERS": {
        "whatsapp": "shopman.shop.adapters.otp_manychat.ManychatOTPSender",
    },
}
_MANYCHAT_OTP_CONFIG = {
    "api_token": "test-token",
    "base_url": "https://api.manychat.invalid/fb",
    "timeout": 1,
    "resolver": (
        "shopman.guestman.contrib.manychat.resolver."
        "ManychatSubscriberResolver.resolve"
    ),
    "otp_resolver": (
        "shopman.guestman.contrib.manychat.resolver."
        "ManychatSubscriberResolver.resolve_active_customer"
    ),
}


@override_settings(
    DOORMAN=_MANYCHAT_OTP_DOORMAN,
    SHOPMAN_MANYCHAT=_MANYCHAT_OTP_CONFIG,
    MANYCHAT_API_TOKEN="test-token",
)
def test_otp_intent_is_committed_before_manychat_io_and_blocks_deletion(
    customer,
    monkeypatch,
):
    provider_entered = Event()
    release_provider = Event()

    monkeypatch.setattr(
        ManychatSubscriberResolver,
        "_lookup_by_whatsapp_id_custom_field_api",
        classmethod(lambda cls, phone: None),
    )

    def lookup_after_commits(cls, phone):
        provider_entered.set()
        assert release_provider.wait(10)
        return 987654321

    monkeypatch.setattr(
        ManychatSubscriberResolver,
        "_lookup_by_phone_api",
        classmethod(lookup_after_commits),
    )
    monkeypatch.setattr(
        ManychatSubscriberResolver,
        "_mirror_whatsapp_id_custom_field_api",
        classmethod(lambda cls, subscriber_id, phone: True),
    )
    monkeypatch.setattr(ManychatOTPSender, "_api_call", lambda *args, **kwargs: True)

    request = Worker(lambda: AuthService.request_code(customer.phone))

    def delete_while_delivery_is_pending():
        try:
            account_privacy.delete_account(
                customer=Customer.objects.get(pk=customer.pk),
                idempotency_key=str(uuid.uuid4()),
                authorized_at=timezone.now(),
            )
        except account_privacy.AccountDeletionBlocked as exc:
            return exc.reason
        return "deleted"

    with ThreadPoolExecutor(max_workers=2) as pool:
        requested = pool.submit(request)
        assert provider_entered.wait(10)

        # Independent connection can see both durable intents before provider
        # I/O returns; neither is an inner savepoint hidden from deletion.
        code = VerificationCode.objects.get(customer_id=customer.uuid)
        assert code.status == VerificationCode.Status.PENDING
        assert code.delivery_started_at is not None
        customer.refresh_from_db()
        assert customer.metadata["manychat_resolution_pending"] is True

        deleted = pool.submit(Worker(delete_while_delivery_is_pending))
        try:
            assert deleted.result(10) == "otp_delivery_in_flight"
        finally:
            release_provider.set()
        result = requested.result(20)

    assert result.success is True
    code.refresh_from_db()
    assert code.status == VerificationCode.Status.SENT
    assert CustomerIdentifier.objects.filter(
        customer=customer,
        identifier_type=IdentifierType.MANYCHAT,
        identifier_value="987654321",
    ).exists()


@override_settings(
    DOORMAN=_MANYCHAT_OTP_DOORMAN,
    SHOPMAN_MANYCHAT=_MANYCHAT_OTP_CONFIG,
    MANYCHAT_API_TOKEN="test-token",
)
def test_deletion_wins_before_otp_prepare_and_no_provider_runs(customer, monkeypatch):
    deletion_locked = Event()
    release_deletion = Event()
    provider_calls = []

    def forbidden_provider(*args, **kwargs):
        provider_calls.append((args, kwargs))
        raise AssertionError("provider must not run after deletion wins")

    monkeypatch.setattr(
        ManychatSubscriberResolver,
        "_lookup_by_whatsapp_id_custom_field_api",
        classmethod(forbidden_provider),
    )
    monkeypatch.setattr(ManychatOTPSender, "_api_call", forbidden_provider)

    def delete_subject():
        from shopman.shop.services import account as account_service

        with transaction.atomic():
            locked = Customer.objects.select_for_update().get(pk=customer.pk)
            locked.is_active = False
            locked.phone = ""
            locked.save(update_fields=["is_active", "phone"])
            account_service._anonymize_order_trail(
                customer_ref=locked.ref,
                phone=customer.phone,
                pseudonym="ANON-otp-delete-first",
            )
            deletion_locked.set()
            assert release_deletion.wait(10)

    deletion = Worker(delete_subject)
    request = Worker(lambda: AuthService.request_code(customer.phone))
    with ThreadPoolExecutor(max_workers=2) as pool:
        deleted = pool.submit(deletion)
        assert deletion_locked.wait(10)
        requested = pool.submit(request)
        try:
            _assert_database_wait(request)
        finally:
            release_deletion.set()
        assert deleted.result(20) is None
        result = requested.result(20)

    assert result.success is False
    assert result.error_code == ErrorCode.ACCOUNT_INACTIVE
    assert provider_calls == []
    assert not VerificationCode.objects.filter(customer_id=customer.uuid).exists()


def test_deletion_wins_before_otp_reconciliation_cannot_restore_sent(customer):
    code = VerificationCode.objects.create(
        target_value=customer.phone,
        purpose=VerificationCode.Purpose.LOGIN,
        customer_id=customer.uuid,
        status=VerificationCode.Status.PENDING,
        delivery_started_at=timezone.now(),
    )
    deletion_locked = Event()
    release_deletion = Event()

    def delete_subject():
        with transaction.atomic():
            locked = Customer.objects.select_for_update().get(pk=customer.pk)
            locked.is_active = False
            locked.phone = ""
            locked.save(update_fields=["is_active", "phone"])
            deletion_locked.set()
            assert release_deletion.wait(10)

    def reconcile_accepted():
        try:
            call_command(
                "reconcile_otp_delivery_privacy",
                code_id=str(code.pk),
                outcome="accepted",
                evidence_ref="provider-ticket/OTP-PG-001",
                stdout=StringIO(),
            )
        except CommandError as exc:
            return str(exc)
        return "accepted"

    deletion = Worker(delete_subject)
    reconciliation = Worker(reconcile_accepted)
    with ThreadPoolExecutor(max_workers=2) as pool:
        deleted = pool.submit(deletion)
        assert deletion_locked.wait(10)
        reconciled = pool.submit(reconciliation)
        try:
            _assert_database_wait(reconciliation)
        finally:
            release_deletion.set()
        assert deleted.result(20) is None
        result = reconciled.result(20)

    assert "contato mudou" in result
    code.refresh_from_db()
    assert code.status == VerificationCode.Status.PENDING
    assert code.delivery_reconciled_at is None
