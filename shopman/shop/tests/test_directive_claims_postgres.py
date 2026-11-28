"""O desfecho atrasado não pode sobrescrever o reaper ou o próximo executor."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Event
from unittest.mock import Mock

import pytest
from django.db import connection, connections
from django.utils import timezone
from shopman.orderman import dispatch, registry
from shopman.orderman.exceptions import DirectiveTerminalError, DirectiveTransientError
from shopman.orderman.management.commands.process_directives import _reap_stuck_directives
from shopman.orderman.models import Directive, Order

from shopman.shop.services.customer_orders import _resolve_due_directive_for_order

requires_postgres = pytest.mark.skipif(connection.vendor != "postgresql", reason="Requires PostgreSQL independent connections")
pytestmark = [pytest.mark.django_db(transaction=True), requires_postgres]


@pytest.mark.parametrize("consumer", ["inline", "customer"])
@pytest.mark.parametrize("outcome", ["success", "terminal", "transient", "unexpected"])
@pytest.mark.parametrize("reclaim", [False, True])
def test_stale_outcome_preserves_reaper_and_new_claim(consumer, outcome, reclaim, monkeypatch):
    entered, release = Event(), Event()
    terminal_hook = Mock()
    topic = "test.claim.concurrent"
    order = Order.objects.create(ref="CLAIM-RACE", status="accepted", channel_ref="web", data={})
    directive = Directive.objects.create(
        topic=topic, payload={"order_ref": order.ref}, available_at=timezone.now() + timedelta(days=1),
    )
    Directive.objects.filter(pk=directive.pk).update(available_at=timezone.now() - timedelta(seconds=1))

    class Handler:
        on_terminal_failure = terminal_hook

        def handle(self, *, message, ctx):
            entered.set()
            assert release.wait(10), "o ensaio não liberou o handler antigo"
            if outcome == "terminal":
                raise DirectiveTerminalError("executor antigo")
            if outcome == "transient":
                raise DirectiveTransientError("executor antigo")
            if outcome == "unexpected":
                raise RuntimeError("executor antigo")

    handler = Handler()
    original_lookup = registry.get_directive_handler
    monkeypatch.setattr(registry, "get_directive_handler", lambda ref: handler if ref == topic else original_lookup(ref))

    def execute():
        try:
            if consumer == "inline":
                return dispatch._process_directive(Directive.objects.get(pk=directive.pk))
            return _resolve_due_directive_for_order(
                Order.objects.get(pk=order.pk), topic=topic, handler=handler, log_name="claim_race",
            )
        finally:
            connections.close_all()

    fields = ("status", "attempts", "started_at", "available_at", "error_code", "last_error")
    with ThreadPoolExecutor(max_workers=1) as pool:
        job = pool.submit(execute)
        try:
            assert entered.wait(10), "o handler não iniciou em conexão independente"
            assert _reap_stuck_directives(timeout_minutes=0, max_attempts=5) == 1
            if reclaim:
                Directive.objects.filter(pk=directive.pk).update(
                    status=Directive.Status.RUNNING, attempts=2, started_at=timezone.now(),
                    error_code="", last_error="novo executor",
                )
            expected = Directive.objects.values(*fields).get(pk=directive.pk)
        finally:
            release.set()
        result = job.result(timeout=10)
    assert Directive.objects.values(*fields).get(pk=directive.pk) == expected
    terminal_hook.assert_not_called()
    if consumer == "customer":
        assert result is False
