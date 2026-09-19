"""Concierge respeita a cerca canônica da exclusão em PostgreSQL.

O ensaio usa conexões independentes e observa a espera real no banco. Assim a
prova não depende de ``sleep``: quando a exclusão vence ``Customer``, tanto o
vínculo explícito quanto a identificação automática recusam a resolução lida
antes da trava e não restauram PII numa conversa órfã.
"""

from __future__ import annotations

import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from time import monotonic

import pytest
from django.db import close_old_connections, connection, connections
from django.utils import timezone
from shopman.guestman.models import Customer

from shopman.shop.models import Conversation, ConversationBinding
from shopman.shop.services import account as account_service
from shopman.storefront.concierge import service, transport
from shopman.storefront.concierge.contracts import IdentityResolution, TransportScope
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
            try:
                return self.command()
            except Exception as exc:
                return {"exception": type(exc).__name__, "code": getattr(exc, "code", "")}
        finally:
            connections.close_all()


def _assert_database_wait(worker: Worker) -> None:
    assert worker.started.wait(10)
    deadline = monotonic() + 10
    while monotonic() < deadline:
        with connection.cursor() as cursor:
            cursor.execute("SELECT cardinality(pg_blocking_pids(%s))", [worker.pid])
            if cursor.fetchone()[0] > 0:
                return
        Event().wait(0.01)
    pytest.fail(f"Conexão {worker.pid} não esperou pela trava do titular")


def _customer(suffix: str) -> Customer:
    return Customer.objects.create(
        ref=f"CUS-CONCIERGE-PRIV-{suffix}",
        first_name="Ana",
        last_name="Silva",
        phone=f"+5543999920{suffix}",
    )


def _scope(settings) -> TransportScope:
    settings.SHOPMAN_CONCIERGE = {
        "enabled": True,
        "contract_version": 3,
        "connections": {
            "tiktok-dm": {
                "active": True,
                "provider": "tiktok",
                "account": "tiktok-business",
                "channel": "direct_message",
                "adapter_path": "shopman.storefront.tests.support.concierge_fake.OpaqueAdapter",
                "options": {
                    "allowed_subjects": ["tiktok-subject"],
                    "identity_link_enabled": True,
                },
            }
        },
    }
    return TransportScope(
        provider="tiktok",
        account="tiktok-business",
        channel="direct_message",
        subject="tiktok-subject",
        connection_key="tiktok-dm",
    )


def _paused_deletion(customer: Customer, monkeypatch):
    locked, release = Event(), Event()
    original = account_service.anonymize_customer

    def pause_after_customer_lock(subject, *, correlation_ref=""):
        locked.set()
        assert release.wait(10)
        return original(subject, correlation_ref=correlation_ref)

    monkeypatch.setattr(account_service, "anonymize_customer", pause_after_customer_lock)
    return (
        Worker(
            lambda: account_privacy.delete_account(
                customer=customer,
                idempotency_key=str(uuid.uuid4()),
                authorized_at=timezone.now(),
            )
        ),
        locked,
        release,
    )


def _pause_after_concierge_customer_lock(monkeypatch):
    locked, release = Event(), Event()
    original = service._lock_resolved_customer

    def pause(resolution):
        resolved = original(resolution)
        locked.set()
        assert release.wait(10)
        return resolved

    monkeypatch.setattr(service, "_lock_resolved_customer", pause)
    return locked, release


@pytest.mark.parametrize("operation", ["attach", "identify"])
def test_deletion_wins_before_concierge_identity_write(
    settings,
    monkeypatch,
    operation,
):
    customer = _customer("01" if operation == "attach" else "02")
    scope = _scope(settings)
    resolution = IdentityResolution(
        customer_uuid=customer.uuid,
        assurance="verified_customer",
        phone=customer.phone,
        name=customer.name,
    )
    conversation = Conversation.objects.create(channel_ref="web")
    binding = None
    if operation == "identify":
        binding = ConversationBinding.objects.create(
            conversation=conversation,
            provider=scope.provider,
            account=scope.account,
            transport_channel=scope.channel,
            subject=scope.subject,
            connection_key=scope.connection_key,
            status=ConversationBinding.Status.ACTIVE,
            identity_assurance=ConversationBinding.IdentityAssurance.TRANSPORT_SUBJECT,
            activated_at=timezone.now(),
        )
        monkeypatch.setattr(transport, "identity_for", lambda *_args, **_kwargs: resolution)

    deletion, customer_locked, release = _paused_deletion(customer, monkeypatch)
    if operation == "attach":
        identity_write = Worker(lambda: service.attach_binding(conversation.pk, scope, resolution))
    else:
        identity_write = Worker(lambda: service.identify(conversation, binding))

    with ThreadPoolExecutor(max_workers=2) as pool:
        deleted = pool.submit(deletion)
        try:
            assert customer_locked.wait(10)
            wrote_identity = pool.submit(identity_write)
            _assert_database_wait(identity_write)
        finally:
            release.set()
        deletion_result = deleted.result(20)
        identity_result = wrote_identity.result(20)

    assert not isinstance(deletion_result, dict), deletion_result
    assert deletion_result.replayed is False
    conversation.refresh_from_db()
    assert conversation.customer_ref == conversation.phone == conversation.customer_name == ""
    if operation == "attach":
        assert identity_result == {
            "exception": "BindingAttachmentRejected",
            "code": "identity_unverified",
        }
        assert not ConversationBinding.objects.filter(subject=scope.subject).exists()
    else:
        assert not isinstance(identity_result, dict), identity_result
        binding.refresh_from_db()
        assert binding.identity_assurance == ConversationBinding.IdentityAssurance.TRANSPORT_SUBJECT


@pytest.mark.parametrize("operation", ["attach", "identify"])
def test_concierge_identity_write_wins_then_deletion_removes_the_conversation(
    settings,
    monkeypatch,
    operation,
):
    customer = _customer("03" if operation == "attach" else "04")
    scope = _scope(settings)
    resolution = IdentityResolution(
        customer_uuid=customer.uuid,
        assurance="verified_customer",
        phone=customer.phone,
        name=customer.name,
    )
    conversation = Conversation.objects.create(channel_ref="web")
    binding = None
    if operation == "identify":
        binding = ConversationBinding.objects.create(
            conversation=conversation,
            provider=scope.provider,
            account=scope.account,
            transport_channel=scope.channel,
            subject=scope.subject,
            connection_key=scope.connection_key,
            status=ConversationBinding.Status.ACTIVE,
            identity_assurance=ConversationBinding.IdentityAssurance.TRANSPORT_SUBJECT,
            activated_at=timezone.now(),
        )
        monkeypatch.setattr(transport, "identity_for", lambda *_args, **_kwargs: resolution)

    concierge_locked, release = _pause_after_concierge_customer_lock(monkeypatch)
    if operation == "attach":
        identity_write = Worker(lambda: service.attach_binding(conversation.pk, scope, resolution))
    else:
        identity_write = Worker(lambda: service.identify(conversation, binding))
    deletion = Worker(
        lambda: account_privacy.delete_account(
            customer=customer,
            idempotency_key=str(uuid.uuid4()),
            authorized_at=timezone.now(),
        )
    )

    with ThreadPoolExecutor(max_workers=2) as pool:
        wrote_identity = pool.submit(identity_write)
        try:
            assert concierge_locked.wait(10)
            deleted = pool.submit(deletion)
            _assert_database_wait(deletion)
        finally:
            release.set()
        identity_result = wrote_identity.result(20)
        deletion_result = deleted.result(20)

    assert not isinstance(identity_result, dict), identity_result
    assert not isinstance(deletion_result, dict), deletion_result
    assert deletion_result.replayed is False
    assert not Conversation.objects.filter(pk=conversation.pk).exists()
    assert not ConversationBinding.objects.filter(conversation_id=conversation.pk).exists()
