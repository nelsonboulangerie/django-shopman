"""Corridas reais entre exclusão de conta e novos efeitos pessoais.

SQLite não implementa ``SELECT FOR UPDATE``. Estes ensaios usam duas conexões
PostgreSQL para provar a cerca canônica no ``Customer``: depois que a exclusão
vence essa trava, mutações da conta, checkout, inscrição e envio direto não
podem recriar PII nem cruzar um provider externo.
"""

from __future__ import annotations

import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Event
from time import monotonic

import pytest
from django.db import close_old_connections, connection, connections
from django.utils import timezone
from shopman.guestman.contrib.consent.models import CommunicationConsent
from shopman.guestman.models import Customer, CustomerAddress
from shopman.orderman.models import Order, Session
from shopman.orderman.services.commit import CommitService

from shopman.shop.models import (
    DeliveryAttempt,
    DeliveryTarget,
    PrivacyRequestReceipt,
    PrivacyRequestState,
)
from shopman.shop.services import account as account_service
from shopman.shop.services.marketing_contracts import ResolvedDispatchArtifact
from shopman.shop.services.marketing_delivery_attempts import execute_target
from shopman.shop.services.marketing_delivery_worker import (
    claim_due_targets,
    fanout_in_chunks,
    queue_materialized_targets,
)
from shopman.shop.tests.test_marketing_delivery_ledger import _graph
from shopman.storefront.intents.types import AddressIntent, ProfileUpdateIntent
from shopman.storefront.models import StockAlertSubscription
from shopman.storefront.services import account_privacy, stock_alerts

requires_postgres = pytest.mark.skipif(
    connection.vendor != "postgresql",
    reason="Requires independent PostgreSQL connections and row locks",
)

pytestmark = [pytest.mark.django_db(transaction=True), requires_postgres]


class Worker:
    """Executa uma operação numa conexão independente e torna a espera observável."""

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
            except Exception as exc:  # o chamador verifica o contrato estruturado
                return {
                    "exception": type(exc).__name__,
                    "code": getattr(exc, "code", ""),
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
    pytest.fail(f"Conexão {worker.pid} não esperou pela trava do titular")


def _customer(suffix: str) -> Customer:
    return Customer.objects.create(
        ref=f"CUS-PRIV-RACE-{suffix}",
        first_name="Ana",
        last_name="Silva",
        phone=f"+5543999910{suffix}",
        email=f"privacy-race-{suffix}@example.com",
        birthday=timezone.localdate().replace(year=timezone.localdate().year - 30),
    )


def _paused_deletion(customer: Customer, monkeypatch):
    locked, release = Event(), Event()
    original = account_service.anonymize_customer

    def pause_after_subject_lock(subject):
        # delete_account já possui SELECT FOR UPDATE no Customer neste ponto.
        locked.set()
        assert release.wait(10)
        return original(subject)

    monkeypatch.setattr(account_service, "anonymize_customer", pause_after_subject_lock)
    worker = Worker(
        lambda: account_privacy.delete_account(
            customer=customer,
            idempotency_key=str(uuid.uuid4()),
            authorized_at=timezone.now(),
        )
    )
    return worker, locked, release


def test_deletion_wins_against_checkout_without_leaving_a_personal_order(monkeypatch):
    customer = _customer("01")
    Session.objects.create(
        session_key="privacy-race-checkout",
        channel_ref="web",
        items=[{"sku": "PRIVACY-RACE", "qty": 1, "unit_price_q": 1000}],
        data={
            "customer_ref": customer.ref,
            "customer": {"ref": customer.ref, "phone": customer.phone},
        },
    )
    deletion, subject_locked, release = _paused_deletion(customer, monkeypatch)
    checkout = Worker(
        lambda: CommitService.commit(
            session_key="privacy-race-checkout",
            channel_ref="web",
            idempotency_key="privacy-race-checkout-idempotency",
        )
    )

    with ThreadPoolExecutor(max_workers=2) as pool:
        deleted = pool.submit(deletion)
        try:
            assert subject_locked.wait(10)
            committed = pool.submit(checkout)
            _assert_database_wait(checkout)
        finally:
            release.set()
        deletion_result = deleted.result(20)
        checkout_result = committed.result(20)

    assert deletion_result.replayed is False
    assert checkout_result == {"exception": "CommitError", "code": "customer_inactive"}
    assert not Order.objects.filter(session_key="privacy-race-checkout").exists()


def test_deletion_wins_against_stock_alert_without_recreating_contact(monkeypatch):
    customer = _customer("02")
    deletion, subject_locked, release = _paused_deletion(customer, monkeypatch)
    subscribe = Worker(
        lambda: stock_alerts.subscribe_with_outcome(
            "PRIVACY-RACE",
            customer=customer,
            phone=customer.phone,
            disclosure_text=stock_alerts.STOCK_ALERT_DISCLOSURE,
            disclosure_version=stock_alerts.STOCK_ALERT_DISCLOSURE_VERSION,
            adult_declared=True,
        )
    )

    with ThreadPoolExecutor(max_workers=2) as pool:
        deleted = pool.submit(deletion)
        try:
            assert subject_locked.wait(10)
            subscribed = pool.submit(subscribe)
            _assert_database_wait(subscribe)
        finally:
            release.set()
        deletion_result = deleted.result(20)
        subscription_result = subscribed.result(20)

    assert deletion_result.replayed is False
    assert subscription_result.subscription is None
    assert subscription_result.created is False
    assert not StockAlertSubscription.objects.filter(sku="PRIVACY-RACE").exists()


@pytest.mark.parametrize("mutation", ("address", "profile", "consent"))
def test_deletion_wins_against_personal_account_mutations(monkeypatch, mutation):
    customer = _customer({"address": "03", "profile": "04", "consent": "05"}[mutation])
    operations = {
        "address": lambda: account_service.add_address(
            customer.ref,
            AddressIntent(
                label="home",
                label_custom="",
                formatted_address="Rua criada tarde demais, 10",
                route="Rua criada tarde demais",
                street_number="10",
                neighborhood="Centro",
                city="Londrina",
                state_code="PR",
                postal_code="86000-000",
                complement="",
                delivery_instructions="",
                place_id=None,
                is_default=False,
                coordinates=None,
                is_verified=False,
            ),
        ),
        "profile": lambda: account_service.update_profile(
            customer.ref,
            ProfileUpdateIntent(first_name="Nome recriado"),
        ),
        "consent": lambda: account_service.set_notification_consent(
            customer.ref,
            "whatsapp",
            enabled=True,
        ),
    }
    deletion, subject_locked, release = _paused_deletion(customer, monkeypatch)
    mutate = Worker(operations[mutation])

    with ThreadPoolExecutor(max_workers=2) as pool:
        deleted = pool.submit(deletion)
        try:
            assert subject_locked.wait(10)
            mutated = pool.submit(mutate)
            _assert_database_wait(mutate)
        finally:
            release.set()
        deletion_result = deleted.result(20)
        mutation_result = mutated.result(20)

    assert deletion_result.replayed is False
    assert mutation_result["exception"] in {"AccountUnavailable", "DoesNotExist"}
    assert not CustomerAddress.objects.filter(customer=customer).exists()
    assert not CommunicationConsent.objects.filter(customer=customer).exists()
    customer.refresh_from_db()
    assert customer.is_active is False
    assert customer.first_name == "Anonimizado"


def test_two_deletion_keys_serialize_to_one_effect_and_two_completed_receipts(monkeypatch):
    customer = _customer("06")
    first, subject_locked, release = _paused_deletion(customer, monkeypatch)
    second = Worker(
        lambda: account_privacy.delete_account(
            customer=customer,
            idempotency_key=str(uuid.uuid4()),
            authorized_at=timezone.now(),
        )
    )

    with ThreadPoolExecutor(max_workers=2) as pool:
        first_result = pool.submit(first)
        try:
            assert subject_locked.wait(10)
            second_result = pool.submit(second)
            _assert_database_wait(second)
        finally:
            release.set()
        original = first_result.result(20)
        replay = second_result.result(20)

    assert original.replayed is False
    assert replay.replayed is True
    receipts = list(PrivacyRequestReceipt.objects.order_by("pk"))
    assert len(receipts) == 2
    assert all(receipt.state == PrivacyRequestState.COMPLETED for receipt in receipts)


class RecordingProvider:
    def __init__(self):
        self.calls = []

    def send(self, **kwargs):  # pragma: no cover - a cerca deve tornar isto inalcançável
        self.calls.append(kwargs)
        raise AssertionError("o provider não pode ser chamado após a exclusão vencer")


def test_deletion_wins_against_direct_marketing_before_provider_boundary(monkeypatch):
    outbox, members = _graph(
        platform="whatsapp",
        suffix="privacy-deletion-race",
        target_keys=("privacy-recipient",),
    )
    customer = members[0].customer
    fanout_in_chunks(outbox.ref)
    assert queue_materialized_targets(outbox.ref) == 1
    claimed = claim_due_targets(worker_id="privacy-race-worker")
    target = claimed.targets[0]
    assert target.member_id == members[0].pk

    artifact = ResolvedDispatchArtifact(
        platform="whatsapp",
        body="Fornada pronta",
        content_version=2,
    )
    provider = RecordingProvider()
    deletion, subject_locked, release = _paused_deletion(customer, monkeypatch)
    send = Worker(
        lambda: execute_target(
            target.ref,
            provider=provider,
            artifact=artifact,
            idempotency_token="privacy-race-provider-token",
            request_hash=artifact.artifact_hash,
            worker_id="privacy-race-worker",
            now=timezone.now() + timedelta(seconds=1),
        )
    )

    with ThreadPoolExecutor(max_workers=2) as pool:
        deleted = pool.submit(deletion)
        try:
            assert subject_locked.wait(10)
            sent = pool.submit(send)
            _assert_database_wait(send)
        finally:
            release.set()
        deletion_result = deleted.result(20)
        send_result = sent.result(20)

    assert deletion_result.replayed is False
    assert send_result.provider_called is False
    assert provider.calls == []
    target.refresh_from_db()
    attempt = DeliveryAttempt.objects.get(target=target)
    assert target.state == DeliveryTarget.State.CANCELLED
    assert attempt.error_code == "recipient_account_inactive"
