"""PostgreSQL proofs for Guestman child writers and canonical lock order."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Event
from time import monotonic

import pytest
from django.db import close_old_connections, connection, connections, transaction
from shopman.guestman.contrib.identifiers.models import CustomerIdentifier, IdentifierType
from shopman.guestman.contrib.identifiers.service import IdentifierService
from shopman.guestman.contrib.insights.models import CustomerInsight
from shopman.guestman.contrib.insights.service import InsightService
from shopman.guestman.contrib.loyalty.models import LoyaltyAccount, LoyaltyTransaction
from shopman.guestman.contrib.loyalty.service import LoyaltyService
from shopman.guestman.contrib.preferences.models import CustomerPreference
from shopman.guestman.contrib.preferences.service import PreferenceService
from shopman.guestman.contrib.timeline.models import TimelineEvent
from shopman.guestman.contrib.timeline.service import TimelineService
from shopman.guestman.models import Customer

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
    pytest.fail(f"Connection {worker.pid} did not wait for the canonical Customer lock")


def _close_customer_and_children(customer_pk, locked: Event, release: Event):
    """Minimal deletion winner: inactive owner plus all scoped child records gone."""
    with transaction.atomic():
        customer = Customer.objects.select_for_update().get(pk=customer_pk)
        customer.is_active = False
        customer.save(update_fields=["is_active", "updated_at"])
        CustomerIdentifier.objects.filter(customer=customer).delete()
        CustomerPreference.objects.filter(customer=customer).delete()
        TimelineEvent.objects.filter(customer=customer).delete()
        CustomerInsight.objects.filter(customer=customer).delete()
        LoyaltyAccount.objects.filter(customer=customer).delete()
        customer.tags.clear()
        locked.set()
        assert release.wait(10)


def _mutation(customer_ref: str, name: str):
    if name == "identifier_add":
        return IdentifierService.add_identifier(
            customer_ref,
            IdentifierType.INSTAGRAM,
            "privacy-race",
        )
    if name == "identifier_ensure":
        return IdentifierService.ensure_identifier(
            customer_ref,
            IdentifierType.INSTAGRAM,
            "privacy-race",
        )
    if name == "preference_set":
        return PreferenceService.set_preference(
            customer_ref,
            "alimentar",
            "sem_lactose",
            True,
        )
    if name == "preference_delete":
        return PreferenceService.delete_preference(
            customer_ref,
            "alimentar",
            "sem_lactose",
        )
    if name == "timeline":
        return TimelineService.log_event(customer_ref, "note", "Não pode voltar")
    if name == "insight":
        return InsightService.recalculate(customer_ref)
    if name == "loyalty_enroll":
        return LoyaltyService.enroll(customer_ref)
    if name == "loyalty_earn":
        return LoyaltyService.earn_points(customer_ref, 10, "Compra")
    raise AssertionError(f"Unknown mutation {name}")


@pytest.mark.parametrize(
    "mutation_name",
    (
        "identifier_add",
        "identifier_ensure",
        "preference_set",
        "preference_delete",
        "timeline",
        "insight",
        "loyalty_enroll",
        "loyalty_earn",
    ),
)
def test_deletion_wins_without_guestman_child_recreation(customer, mutation_name):
    if mutation_name == "loyalty_earn":
        LoyaltyService.enroll(customer.ref)

    locked, release = Event(), Event()
    deletion = Worker(
        lambda: _close_customer_and_children(customer.pk, locked, release)
    )
    mutation = Worker(lambda: _mutation(customer.ref, mutation_name))

    with ThreadPoolExecutor(max_workers=2) as pool:
        deleted = pool.submit(deletion)
        try:
            assert locked.wait(10)
            mutated = pool.submit(mutation)
            _assert_database_wait(mutation)
        finally:
            release.set()
        assert deleted.result(20) is None
        mutation_result = mutated.result(20)

    if mutation_name == "preference_delete":
        assert mutation_result is False
    elif mutation_name == "loyalty_earn":
        assert mutation_result == {
            "exception": "CustomerError",
            "code": "LOYALTY_NOT_ENROLLED",
        }
    else:
        assert mutation_result["exception"] == "DoesNotExist"

    customer.refresh_from_db()
    assert customer.is_active is False
    assert not CustomerIdentifier.objects.filter(customer=customer).exists()
    assert not CustomerPreference.objects.filter(customer=customer).exists()
    assert not TimelineEvent.objects.filter(customer=customer).exists()
    assert not CustomerInsight.objects.filter(customer=customer).exists()
    assert not LoyaltyAccount.objects.filter(customer=customer).exists()


def _hold_customer(customer_pk, locked: Event, release: Event):
    with transaction.atomic():
        Customer.objects.select_for_update().get(pk=customer_pk)
        locked.set()
        assert release.wait(10)


def test_loyalty_writer_waits_on_customer_before_locking_account(customer):
    account = LoyaltyService.enroll(customer.ref)
    locked, release = Event(), Event()
    customer_holder = Worker(lambda: _hold_customer(customer.pk, locked, release))
    earn = Worker(lambda: LoyaltyService.earn_points(customer.ref, 10, "Compra"))

    with ThreadPoolExecutor(max_workers=2) as pool:
        holding = pool.submit(customer_holder)
        try:
            assert locked.wait(10)
            earning = pool.submit(earn)
            _assert_database_wait(earn)

            # If earn had locked LoyaltyAccount before waiting for Customer,
            # this NOWAIT would fail and the global order would be inverted.
            with transaction.atomic():
                locked_account = LoyaltyAccount.objects.select_for_update(nowait=True).get(
                    pk=account.pk,
                )
                assert locked_account.pk == account.pk
        finally:
            release.set()
        assert holding.result(20) is None
        earn_result = earning.result(20)

    assert not isinstance(earn_result, dict), earn_result
    account.refresh_from_db()
    assert account.points_balance == 10
    assert LoyaltyTransaction.objects.filter(account=account).count() == 1
