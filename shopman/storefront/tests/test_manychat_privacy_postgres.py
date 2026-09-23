"""PostgreSQL proofs for ManyChat identity sync versus account deletion."""

from __future__ import annotations

import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from time import monotonic

import pytest
from django.db import close_old_connections, connection, connections
from django.test import override_settings
from django.utils import timezone
from shopman.guestman.contrib.identifiers.models import (  # noqa: E402
    CustomerIdentifier,
    IdentifierType,
)
from shopman.guestman.contrib.manychat.resolver import (  # noqa: E402
    ManychatSubscriberResolver,
    _ProviderCreateOutcome,
    _ProviderLookupOutcome,
)
from shopman.guestman.contrib.manychat.service import ManychatService  # noqa: E402
from shopman.guestman.models import (  # noqa: E402
    Customer,
    ProviderErasureTombstone,
    erasure_digest,
)

from shopman.shop.services import account as account_service  # noqa: E402
from shopman.storefront.services import account_privacy  # noqa: E402

requires_postgres = pytest.mark.skipif(
    connection.vendor != "postgresql",
    reason="Requires independent PostgreSQL connections and row locks",
)

pytestmark = [pytest.mark.django_db(transaction=True), requires_postgres]


def _provider_confirms(monkeypatch, *, custom_fields=None):
    """O ManyChat confirmando a limpeza — o único jeito de haver "pronto".

    Sem esta confirmação explícita a exclusão falha FECHADO, que é a resposta
    certa quando o provedor não responde. Por isso todo caminho feliz precisa
    dizer, no próprio teste, que ele confirmou.
    """
    monkeypatch.setattr(
        ManychatSubscriberResolver,
        "fetch_subscriber_info",
        classmethod(lambda cls, subscriber_id: {"custom_fields": custom_fields or []}),
    )
    import shopman.shop.adapters.notification_manychat as adapter

    monkeypatch.setattr(adapter, "set_custom_field", lambda *args, **kwargs: True)


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
                return {
                    "exception": type(exc).__name__,
                    "code": getattr(exc, "code", ""),
                    "reason": getattr(exc, "reason", ""),
                }
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
    pytest.fail(f"Connection {worker.pid} did not wait for the canonical Customer lock")


def _customer(suffix: str) -> Customer:
    return Customer.objects.create(
        ref=f"CUS-MANYCHAT-PRIV-{suffix}",
        first_name="Ana",
        last_name="Silva",
        phone=f"+5543999777{suffix}",
        email=f"manychat-privacy-{suffix}@example.com",
    )


def _subscriber(customer: Customer, suffix: str) -> dict:
    return {
        "id": f"manychat-privacy-{suffix}",
        "first_name": "Ana atualizada",
        "whatsapp_id": customer.phone,
    }


def test_manychat_binding_wins_then_deletion_reaches_the_new_link(monkeypatch):
    """Se o writer vence, a exclusão espera e alcança o efeito recém-criado.

    É a frase da matriz canônica, agora com a exclusão CONCLUINDO em vez de
    recusar: o assinante que o sync acabou de vincular entra na limpeza e ganha
    lápide, sem que ninguém precise pedir nada à equipe.
    """
    customer = _customer("01")
    payload = _subscriber(customer, "01")
    customer_locked = Event()
    release_sync = Event()
    original_lock = ManychatService._lock_active_customer

    def pause_after_customer_lock(customer_pk):
        locked = original_lock(customer_pk)
        customer_locked.set()
        assert release_sync.wait(10)
        return locked

    monkeypatch.setattr(
        ManychatService,
        "_lock_active_customer",
        staticmethod(pause_after_customer_lock),
    )
    _provider_confirms(monkeypatch)
    sync = Worker(lambda: ManychatService.sync_subscriber(payload))
    deletion = Worker(
        lambda: account_privacy.delete_account(
            customer=customer,
            idempotency_key=str(uuid.uuid4()),
            authorized_at=timezone.now(),
        )
    )

    with ThreadPoolExecutor(max_workers=2) as pool:
        synced = pool.submit(sync)
        try:
            assert customer_locked.wait(10)
            deleted = pool.submit(deletion)
            _assert_database_wait(deletion)
        finally:
            release_sync.set()
        sync_result = synced.result(20)
        deletion_result = deleted.result(20)

    assert not isinstance(sync_result, dict), sync_result
    assert sync_result[1] is False
    assert deletion_result is not None and not isinstance(deletion_result, dict), deletion_result
    customer.refresh_from_db()
    assert customer.is_active is False
    assert customer.phone == ""
    # O identificador local sai junto com a conta...
    assert not CustomerIdentifier.objects.filter(
        customer=customer,
        identifier_type=IdentifierType.MANYCHAT,
    ).exists()
    # ...e a lápide fica no lugar dele, para o próximo webhook do MESMO
    # assinante não recriar o cadastro que acabou de ser apagado.
    assert ProviderErasureTombstone.objects.filter(
        digest=erasure_digest("manychat", "subscriber_id", payload["id"]),
    ).exists()


def test_deletion_wins_then_stale_manychat_sync_cannot_restore_pii(monkeypatch):
    customer = _customer("02")
    payload = _subscriber(customer, "02")
    customer_locked = Event()
    release_deletion = Event()
    original_anonymize = account_service.anonymize_customer

    def pause_after_customer_lock(subject, *, correlation_ref=""):
        customer_locked.set()
        assert release_deletion.wait(10)
        return original_anonymize(subject, correlation_ref=correlation_ref)

    monkeypatch.setattr(account_service, "anonymize_customer", pause_after_customer_lock)
    deletion = Worker(
        lambda: account_privacy.delete_account(
            customer=customer,
            idempotency_key=str(uuid.uuid4()),
            authorized_at=timezone.now(),
        )
    )
    sync = Worker(lambda: ManychatService.sync_subscriber(payload))

    with ThreadPoolExecutor(max_workers=2) as pool:
        deleted = pool.submit(deletion)
        try:
            assert customer_locked.wait(10)
            synced = pool.submit(sync)
            _assert_database_wait(sync)
        finally:
            release_deletion.set()
        deletion_result = deleted.result(20)
        sync_result = synced.result(20)

    assert not isinstance(deletion_result, dict), deletion_result
    assert sync_result["exception"] == "ValueError"
    customer.refresh_from_db()
    assert customer.is_active is False
    assert customer.phone == ""
    assert customer.email == ""
    assert not CustomerIdentifier.objects.filter(customer=customer).exists()


@override_settings(MANYCHAT_API_TOKEN="test-token")
def test_deletion_wins_then_stale_resolver_makes_no_provider_call(monkeypatch):
    customer = _customer("03")
    customer_locked = Event()
    release_deletion = Event()
    original_anonymize = account_service.anonymize_customer
    provider_calls = []

    def pause_after_customer_lock(subject, *, correlation_ref=""):
        customer_locked.set()
        assert release_deletion.wait(10)
        return original_anonymize(subject, correlation_ref=correlation_ref)

    def forbidden_provider_call(*args, **kwargs):
        provider_calls.append((args, kwargs))
        raise AssertionError("provider must not run after deletion wins")

    monkeypatch.setattr(account_service, "anonymize_customer", pause_after_customer_lock)
    monkeypatch.setattr(
        ManychatSubscriberResolver,
        "_lookup_by_whatsapp_id_custom_field_api",
        classmethod(forbidden_provider_call),
    )
    monkeypatch.setattr(
        ManychatSubscriberResolver,
        "_lookup_by_phone_api",
        classmethod(forbidden_provider_call),
    )
    monkeypatch.setattr(
        ManychatSubscriberResolver,
        "_create_whatsapp_subscriber_outcome",
        classmethod(forbidden_provider_call),
    )

    deletion = Worker(
        lambda: account_privacy.delete_account(
            customer=customer,
            idempotency_key=str(uuid.uuid4()),
            authorized_at=timezone.now(),
        )
    )
    resolver = Worker(lambda: ManychatSubscriberResolver.resolve(customer.phone))

    with ThreadPoolExecutor(max_workers=2) as pool:
        deleted = pool.submit(deletion)
        try:
            assert customer_locked.wait(10)
            resolved = pool.submit(resolver)
            _assert_database_wait(resolver)
        finally:
            release_deletion.set()
        deletion_result = deleted.result(20)
        resolver_result = resolved.result(20)

    assert not isinstance(deletion_result, dict), deletion_result
    assert resolver_result is None
    assert provider_calls == []


@override_settings(MANYCHAT_API_TOKEN="test-token")
def test_resolver_wins_then_deletion_waits_and_reaches_the_subscriber(monkeypatch):
    customer = _customer("04")
    provider_entered = Event()
    release_provider = Event()

    monkeypatch.setattr(
        ManychatSubscriberResolver,
        "_lookup_by_whatsapp_id_custom_field_api",
        classmethod(lambda cls, phone: None),
    )

    def lookup_after_lock(cls, phone):
        provider_entered.set()
        assert release_provider.wait(10)
        return 876543210

    monkeypatch.setattr(
        ManychatSubscriberResolver,
        "_lookup_by_phone_api",
        classmethod(lookup_after_lock),
    )
    monkeypatch.setattr(
        ManychatSubscriberResolver,
        "_mirror_whatsapp_id_custom_field_api",
        classmethod(lambda cls, subscriber_id, phone: True),
    )
    resolver = Worker(lambda: ManychatSubscriberResolver.resolve(customer.phone))
    deletion = Worker(
        lambda: account_privacy.delete_account(
            customer=customer,
            idempotency_key=str(uuid.uuid4()),
            authorized_at=timezone.now(),
        )
    )

    _provider_confirms(monkeypatch)

    with ThreadPoolExecutor(max_workers=2) as pool:
        resolved = pool.submit(resolver)
        try:
            assert provider_entered.wait(10)
            deleted = pool.submit(deletion)
        finally:
            # A exclusão agora ESPERA o mutex do provedor em vez de recusar de
            # cara: ela não pode mexer no perfil de lá enquanto o resolvedor
            # está dentro dele. Por isso o provedor é liberado ANTES de colher
            # o resultado — segurar os dois seria travar o teste, não o sistema.
            release_provider.set()
        deletion_result = deleted.result(20)
        resolver_result = resolved.result(20)

    assert resolver_result == 876543210
    sepultado = ProviderErasureTombstone.objects.filter(
        digest=erasure_digest("manychat", "subscriber_id", "876543210"),
    ).exists()
    customer.refresh_from_db()

    # Quem vence a corrida varia com o relógio; o INVARIANTE não. A exclusão
    # nunca diz "pronto" sem ter alcançado o assinante que o resolvedor
    # vinculou: ou ela conclui tendo sepultado 876543210, ou ela falha fechada
    # com a conta intacta. O que ela jamais faz é concluir deixando o vínculo
    # vivo — e jamais manda o cliente pedir à equipe.
    if isinstance(deletion_result, dict):
        assert deletion_result["exception"] == "ProviderErasureIncomplete"
        assert customer.is_active is True
        assert sepultado is False
    else:
        assert customer.is_active is False
        assert sepultado is True


@override_settings(MANYCHAT_API_TOKEN="test-token")
def test_crash_after_durable_intent_keeps_deletion_closed(monkeypatch):
    customer = _customer("06")
    intent_committed = Event()
    release_crash = Event()

    def crash_after_intent(cls, customer_pk, recipient):
        intent_committed.set()
        assert release_crash.wait(10)
        raise RuntimeError("simulated process crash before provider response")

    monkeypatch.setattr(
        ManychatSubscriberResolver,
        "_run_pending_customer_resolution",
        classmethod(crash_after_intent),
    )
    resolver = Worker(lambda: ManychatSubscriberResolver.resolve(customer.phone))

    with ThreadPoolExecutor(max_workers=1) as pool:
        resolved = pool.submit(resolver)
        try:
            assert intent_committed.wait(10)
            # This is a different connection from the worker. Seeing the marker
            # here proves phase A committed before provider work began.
            customer.refresh_from_db()
            assert customer.metadata["manychat_resolution_pending"] is True
        finally:
            release_crash.set()
        resolver_result = resolved.result(20)

    assert resolver_result["exception"] == "RuntimeError"
    customer.refresh_from_db()
    assert customer.metadata["manychat_resolution_pending"] is True
    with pytest.raises(account_privacy.ProviderErasureIncomplete) as exc_info:
        account_privacy.delete_account(
            customer=customer,
            idempotency_key=str(uuid.uuid4()),
            authorized_at=timezone.now(),
        )
    assert exc_info.value.reason == "manychat_reconciliation_uncertain"
    customer.refresh_from_db()
    assert customer.is_active is True


@override_settings(MANYCHAT_API_TOKEN="test-token")
def test_uncertain_resolver_outcome_leaves_deletion_closed(monkeypatch):
    customer = _customer("05")
    monkeypatch.setattr(
        ManychatSubscriberResolver,
        "_lookup_by_whatsapp_id_custom_field_api",
        classmethod(lambda cls, phone: None),
    )
    monkeypatch.setattr(
        ManychatSubscriberResolver,
        "_lookup_by_phone_api",
        classmethod(lambda cls, phone: None),
    )
    monkeypatch.setattr(
        ManychatSubscriberResolver,
        "_create_whatsapp_subscriber_outcome",
        classmethod(lambda cls, phone: _ProviderCreateOutcome()),
    )

    assert ManychatSubscriberResolver.resolve(customer.phone) is None
    customer.refresh_from_db()
    assert customer.metadata["manychat_resolution_pending"] is True

    with pytest.raises(account_privacy.ProviderErasureIncomplete) as exc_info:
        account_privacy.delete_account(
            customer=customer,
            idempotency_key=str(uuid.uuid4()),
            authorized_at=timezone.now(),
        )
    assert exc_info.value.reason == "manychat_reconciliation_uncertain"

    monkeypatch.setattr(
        ManychatSubscriberResolver,
        "_lookup_by_phone_api_outcome",
        classmethod(
            lambda cls, phone: _ProviderLookupOutcome(conclusive_absence=True)
        ),
    )
    assert ManychatSubscriberResolver.reconcile_pending(customer.pk) == "absent"
    customer.refresh_from_db()
    assert "manychat_resolution_pending" not in customer.metadata
    assert Customer.objects.count() == 1
