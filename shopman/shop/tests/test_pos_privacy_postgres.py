"""PostgreSQL proofs for account deletion versus POS personal-data writers."""

from __future__ import annotations

import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from time import monotonic

import pytest
from django.db import close_old_connections, connection, connections
from django.test import override_settings
from django.utils import timezone
from shopman.guestman.models import ContactPoint, Customer, CustomerAddress

from shopman.shop.services import account as account_service
from shopman.shop.services.pos import (
    PosCustomerMergeError,
    PosCustomerUnavailable,
    _persist_customer_from_payload,
    merge_pos_customers,
    update_pos_customer_profile,
)
from shopman.storefront.services import account_privacy

requires_postgres = pytest.mark.skipif(
    connection.vendor != "postgresql",
    reason="Requires independent PostgreSQL connections and row locks",
)

pytestmark = [pytest.mark.django_db(transaction=True), requires_postgres]

_PRIVACY_KEYS = override_settings(
    SHOPMAN_PRIVACY_RECEIPT_HMAC_KEY="test-only-privacy-receipt-hmac-key-v2",
    SHOPMAN_PRIVACY_RECEIPT_HMAC_KEY_VERSION=2,
    SHOPMAN_PRIVACY_RECEIPT_HMAC_PREVIOUS_KEYS={},
)


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
                    "message": str(exc),
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
    pytest.fail(f"Connection {worker.pid} did not wait for the Customer fence")


def _customer(suffix: str) -> Customer:
    return Customer.objects.create(
        ref=f"CUS-POS-PRIVACY-{suffix}",
        first_name="Ana",
        last_name="Silva",
        phone=f"+5543999930{suffix}",
        email=f"pos-privacy-{suffix}@example.com",
    )


def _paused_deletion(customer: Customer, monkeypatch):
    locked = Event()
    release = Event()
    original = account_service.anonymize_customer

    def pause_after_customer_lock(subject, *, correlation_ref=""):
        locked.set()
        assert release.wait(10)
        return original(subject, correlation_ref=correlation_ref)

    monkeypatch.setattr(account_service, "anonymize_customer", pause_after_customer_lock)
    worker = Worker(
        lambda: account_privacy.delete_account(
            customer=customer,
            idempotency_key=str(uuid.uuid4()),
            authorized_at=timezone.now(),
        )
    )
    return worker, locked, release


def _race_after_deletion_lock(deletion, locked, release, mutation):
    with ThreadPoolExecutor(max_workers=2) as pool:
        deleted = pool.submit(deletion)
        assert locked.wait(10)
        mutated = pool.submit(mutation)
        try:
            _assert_database_wait(mutation)
        finally:
            release.set()
        return deleted.result(20), mutated.result(20)


@_PRIVACY_KEYS
def test_deletion_wins_against_composite_pos_customer_persist(monkeypatch):
    customer = _customer("01")
    deletion, locked, release = _paused_deletion(customer, monkeypatch)
    mutation = Worker(
        lambda: _persist_customer_from_payload(
            {
                "customer_ref": customer.ref,
                "customer_name": "Nome que não pode voltar",
                "customer_name_correction": True,
                "customer_phone": "43988887777",
                "customer_contact_correction": True,
                "customer_email": "nova@example.com",
                "customer_tax_id": "52998224725",
                "delivery_address": "Rua que não pode voltar, 10",
            },
            operator_username="op",
        )
    )

    deletion_result, mutation_result = _race_after_deletion_lock(
        deletion,
        locked,
        release,
        mutation,
    )

    assert not isinstance(deletion_result, dict), deletion_result
    assert mutation_result["exception"] == PosCustomerUnavailable.__name__
    customer.refresh_from_db()
    assert customer.is_active is False
    assert customer.first_name == "Anonimizado"
    assert customer.phone == ""
    assert customer.email == ""
    assert customer.document == ""
    assert customer.metadata == {}
    assert not CustomerAddress.objects.filter(customer=customer).exists()
    assert not ContactPoint.objects.filter(customer=customer).exists()


@_PRIVACY_KEYS
def test_deletion_wins_against_pos_profile_update(monkeypatch):
    customer = _customer("02")
    deletion, locked, release = _paused_deletion(customer, monkeypatch)
    mutation = Worker(
        lambda: update_pos_customer_profile(
            customer_ref=customer.ref,
            payload={
                "notes": "não pode voltar",
                "dietary_restrictions": "não pode voltar",
                "fiscal_prefs": {"cpf_na_nota": True},
            },
        )
    )

    deletion_result, mutation_result = _race_after_deletion_lock(
        deletion,
        locked,
        release,
        mutation,
    )

    assert not isinstance(deletion_result, dict), deletion_result
    assert mutation_result["exception"] == PosCustomerUnavailable.__name__
    customer.refresh_from_db()
    assert customer.is_active is False
    assert customer.notes == ""
    assert customer.metadata == {}


@_PRIVACY_KEYS
def test_deletion_wins_against_pos_customer_merge(monkeypatch):
    source = _customer("03")
    target = _customer("04")
    source_address = CustomerAddress.objects.create(
        customer=source,
        label="home",
        formatted_address="Rua da origem, 10",
    )
    deletion, locked, release = _paused_deletion(target, monkeypatch)
    mutation = Worker(
        lambda: merge_pos_customers(
            source_ref=source.ref,
            target_ref=target.ref,
            operator_username="op",
        )
    )

    deletion_result, mutation_result = _race_after_deletion_lock(
        deletion,
        locked,
        release,
        mutation,
    )

    assert not isinstance(deletion_result, dict), deletion_result
    assert mutation_result["exception"] == PosCustomerMergeError.__name__
    source.refresh_from_db()
    target.refresh_from_db()
    source_address.refresh_from_db()
    assert source.is_active is True
    assert target.is_active is False
    assert source_address.customer_id == source.pk
