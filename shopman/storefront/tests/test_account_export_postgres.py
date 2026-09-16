"""PostgreSQL proofs for the account-export/deletion serialization fence."""

from __future__ import annotations

import json
import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from time import monotonic

import pytest
from django.db import close_old_connections, connection, connections
from django.test import override_settings
from django.utils import timezone
from shopman.guestman.models import Customer, CustomerAddress

from shopman.shop.models import PrivacyRequestState
from shopman.shop.services import account as account_service
from shopman.storefront.services import account_export, account_privacy

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
    """Run one command on an independent connection and expose lock waiting."""

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
        ref=f"CUS-EXPORT-RACE-{suffix}",
        first_name="Ana",
        last_name="Silva",
        phone=f"+5543999920{suffix}",
        email=f"export-race-{suffix}@example.com",
    )


def _begin_export(customer: Customer):
    return account_privacy.begin_export(
        customer_uuid=customer.uuid,
        authorized_at=timezone.now(),
    )


@_PRIVACY_KEYS
def test_export_wins_with_complete_snapshot_before_deletion(monkeypatch):
    customer = _customer("01")
    expected_phone = customer.phone
    CustomerAddress.objects.create(
        customer=customer,
        label="home",
        formatted_address="Rua das Flores, 10",
        city="Londrina",
    )
    receipt = _begin_export(customer)
    export_locked = Event()
    release_export = Event()
    original_write = account_export._write_export

    def pause_with_customer_locked(writer, locked_customer):
        export_locked.set()
        assert release_export.wait(10)
        return original_write(writer, locked_customer)

    monkeypatch.setattr(account_export, "_write_export", pause_with_customer_locked)
    export = Worker(
        lambda: account_export.prepare_account_export(
            customer_uuid=customer.uuid,
            receipt_pk=receipt.pk,
        )
    )
    deletion = Worker(
        lambda: account_privacy.delete_account(
            customer=customer,
            idempotency_key=str(uuid.uuid4()),
            authorized_at=timezone.now(),
        )
    )

    with ThreadPoolExecutor(max_workers=2) as pool:
        exported = pool.submit(export)
        assert export_locked.wait(10)
        deleted = pool.submit(deletion)
        try:
            _assert_database_wait(deletion)
        finally:
            release_export.set()
        export_result = exported.result(20)
        deletion_result = deleted.result(20)

    assert not isinstance(export_result, dict), export_result
    artifact, completed_receipt = export_result
    try:
        payload = json.load(artifact)
    finally:
        artifact.close()
    assert payload["customer"]["first_name"] == "Ana"
    assert payload["customer"]["phone"] == expected_phone
    assert len(payload["addresses"]) == 1
    assert payload["addresses"][0]["formatted_address"] == "Rua das Flores, 10"
    assert payload["addresses"][0]["city"] == "Londrina"
    assert completed_receipt.state == PrivacyRequestState.COMPLETED
    assert not isinstance(deletion_result, dict), deletion_result
    customer.refresh_from_db()
    assert customer.is_active is False
    assert customer.phone == ""


@_PRIVACY_KEYS
def test_deletion_wins_and_export_receipt_fails_without_artifact(monkeypatch):
    customer = _customer("02")
    receipt = _begin_export(customer)
    deletion_locked = Event()
    release_deletion = Event()
    original_anonymize = account_service.anonymize_customer

    def pause_deletion(locked_customer, *, correlation_ref=""):
        deletion_locked.set()
        assert release_deletion.wait(10)
        return original_anonymize(locked_customer, correlation_ref=correlation_ref)

    monkeypatch.setattr(account_service, "anonymize_customer", pause_deletion)
    deletion = Worker(
        lambda: account_privacy.delete_account(
            customer=customer,
            idempotency_key=str(uuid.uuid4()),
            authorized_at=timezone.now(),
        )
    )
    export = Worker(
        lambda: account_export.prepare_account_export(
            customer_uuid=customer.uuid,
            receipt_pk=receipt.pk,
        )
    )

    with ThreadPoolExecutor(max_workers=2) as pool:
        deleted = pool.submit(deletion)
        assert deletion_locked.wait(10)
        exported = pool.submit(export)
        try:
            _assert_database_wait(export)
        finally:
            release_deletion.set()
        deletion_result = deleted.result(20)
        export_result = exported.result(20)

    assert not isinstance(deletion_result, dict), deletion_result
    assert isinstance(export_result, dict), export_result
    receipt.refresh_from_db()
    assert receipt.state == PrivacyRequestState.FAILED
    assert receipt.failure_code == "account_export_incomplete"
    assert receipt.outcome_counts == {}
    customer.refresh_from_db()
    assert customer.is_active is False
    assert customer.phone == ""
