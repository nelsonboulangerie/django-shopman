"""Dedupe de directives como garantia no orquestrador.

``create_deduped`` protege o contrato genérico enquanto a tarefa está viva; as
notificações acrescentam um receipt permanente para fechar também a transição
para ``done`` sem impedir reenvios explícitos.
O teste de corrida real (threads) requer PostgreSQL, como os demais testes de
concorrência da suíte.
"""

from __future__ import annotations

import threading
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.conf import settings
from django.core.management import call_command
from django.db import connection, transaction
from django.test import TransactionTestCase
from django.utils import timezone
from shopman.orderman.models import Directive, IdempotencyKey, Order

from shopman.shop.directives import (
    NOTIFICATION_ORIGINAL_RECEIPT_SCOPE,
    NOTIFICATION_RESEND_RECEIPT_SCOPE,
    NOTIFICATION_SEND,
    create_deduped,
)
from shopman.shop.services import notification as notification_svc

pytestmark = pytest.mark.django_db

requires_postgres = pytest.mark.skipif(
    "sqlite" in settings.DATABASES["default"]["ENGINE"],
    reason="Requires PostgreSQL for real concurrency testing",
)

KEY = "notification.send:ORD-DD-1:order_accepted"


def test_create_deduped_creates_when_no_live_duplicate():
    created = create_deduped(NOTIFICATION_SEND, payload={"order_ref": "ORD-DD-1"}, dedupe_key=KEY)
    assert created is not None
    assert Directive.objects.filter(topic=NOTIFICATION_SEND, dedupe_key=KEY).count() == 1


def test_create_deduped_returns_none_on_live_duplicate():
    create_deduped(NOTIFICATION_SEND, payload={}, dedupe_key=KEY)
    duplicate = create_deduped(NOTIFICATION_SEND, payload={}, dedupe_key=KEY)
    assert duplicate is None
    assert Directive.objects.filter(dedupe_key=KEY).count() == 1


def test_create_deduped_does_not_poison_outer_transaction():
    create_deduped(NOTIFICATION_SEND, payload={}, dedupe_key=KEY)
    with transaction.atomic():
        assert create_deduped(NOTIFICATION_SEND, payload={}, dedupe_key=KEY) is None
        # A transação externa continua utilizável após o IntegrityError interno.
        Order.objects.create(ref="ORD-DD-TX", channel_ref="web", total_q=100)
    assert Order.objects.filter(ref="ORD-DD-TX").exists()


def test_notification_send_adopts_a_historical_directive_into_a_permanent_receipt():
    """Rollout não recria efeito anterior só porque ele ainda não tinha receipt."""
    order = Order.objects.create(ref="ORD-DD-RACE", channel_ref="web", total_q=100, data={})
    dedupe_key = f"notification.send:{order.ref}:order_accepted"
    Directive.objects.create(
        topic=NOTIFICATION_SEND, payload={}, dedupe_key=dedupe_key, status="done"
    )

    notification_svc.send(order, "order_accepted")

    assert Directive.objects.filter(dedupe_key=dedupe_key).count() == 1
    receipt = IdempotencyKey.objects.get(
        scope=NOTIFICATION_ORIGINAL_RECEIPT_SCOPE,
        key=dedupe_key,
    )
    assert receipt.response_body["directive_pk"] == Directive.objects.get(
        dedupe_key=dedupe_key
    ).pk


def test_original_notification_stays_deduped_after_directive_is_done():
    order = Order.objects.create(ref="ORD-DD-DONE", channel_ref="web", total_q=100, data={})
    dedupe_key = f"notification.send:{order.ref}:order_accepted"

    with patch("shopman.orderman.dispatch._on_commit_callback"):
        notification_svc.send(order, "order_accepted")
        directive = Directive.objects.get(dedupe_key=dedupe_key)
        directive.status = "done"
        directive.save(update_fields=["status"])
        notification_svc.send(order, "order_accepted")

    assert Directive.objects.filter(dedupe_key=dedupe_key).count() == 1
    assert IdempotencyKey.objects.filter(
        scope=NOTIFICATION_ORIGINAL_RECEIPT_SCOPE,
        key=dedupe_key,
    ).count() == 1


def test_explicit_resends_get_distinct_permanent_identities():
    order = Order.objects.create(ref="ORD-DD-RESEND", channel_ref="web", total_q=100, data={})

    with patch("shopman.orderman.dispatch._on_commit_callback"):
        notification_svc.send(order, "order_accepted")
        original = Directive.objects.get(
            dedupe_key=f"notification.send:{order.ref}:order_accepted"
        )
        original.status = "done"
        original.save(update_fields=["status"])

        first = notification_svc.resend(
            order,
            "order_accepted",
            min_interval_seconds=0,
        )
        first.status = "done"
        first.save(update_fields=["status"])
        second = notification_svc.resend(
            order,
            "order_accepted",
            min_interval_seconds=0,
        )

    assert first.dedupe_key.endswith(":resend:2")
    assert second.dedupe_key.endswith(":resend:3")
    assert IdempotencyKey.objects.filter(
        scope=NOTIFICATION_RESEND_RECEIPT_SCOPE,
    ).count() == 2


def test_notification_receipts_survive_generic_idempotency_cleanup():
    receipts = [
        IdempotencyKey.objects.create(
            scope=scope,
            key=f"receipt-{index}",
            status="done",
        )
        for index, scope in enumerate(
            (
                NOTIFICATION_ORIGINAL_RECEIPT_SCOPE,
                NOTIFICATION_RESEND_RECEIPT_SCOPE,
            ),
        )
    ]
    disposable = IdempotencyKey.objects.create(
        scope="temporary:test",
        key="disposable",
        status="done",
    )
    old = timezone.now() - timedelta(days=30)
    IdempotencyKey.objects.filter(
        pk__in=[receipt.pk for receipt in receipts] + [disposable.pk],
    ).update(created_at=old)

    call_command("cleanup_idempotency_keys", "--days", "7")

    assert IdempotencyKey.objects.filter(
        pk__in=[receipt.pk for receipt in receipts],
    ).count() == 2
    assert not IdempotencyKey.objects.filter(pk=disposable.pk).exists()


@requires_postgres
class TestConcurrentNotificationSend(TransactionTestCase):
    """Duas threads enfileiram a mesma notificação: exatamente UMA directive."""

    def test_concurrent_send_creates_single_directive(self):
        order = Order.objects.create(
            ref="ORD-DD-CONC", channel_ref="web", total_q=100, data={}
        )
        barrier = threading.Barrier(2)
        errors = []

        def worker():
            try:
                barrier.wait(timeout=5)
                # O dispatch pós-commit não interessa aqui — só a criação.
                with patch("shopman.orderman.dispatch._on_commit_callback"):
                    notification_svc.send(order, "order_accepted")
            except Exception as exc:  # noqa: BLE001 — colecionar para assert
                errors.append(exc)
            finally:
                connection.close()

        threads = [threading.Thread(target=worker) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert errors == []
        dedupe_key = f"notification.send:{order.ref}:order_accepted"
        assert Directive.objects.filter(dedupe_key=dedupe_key).count() == 1
