from __future__ import annotations

from django.core.management import call_command
from django.test import TestCase
from shopman.orderman import registry
from shopman.orderman.models import Directive


class DummyDirectiveHandler:
    topic = "dummy.topic"

    def __init__(self) -> None:
        self.calls = 0

    def handle(self, *, message: Directive, ctx: dict) -> None:
        self.calls += 1
        message.status = "done"
        message.save(update_fields=["status", "updated_at"])


class ProcessDirectivesCommandTests(TestCase):
    def setUp(self) -> None:
        super().setUp()
        registry.clear()
        self.handler = DummyDirectiveHandler()
        registry.register_directive_handler(self.handler)

    def tearDown(self) -> None:
        registry.clear()
        super().tearDown()

    def _create_queued(self, topic="dummy.topic", **kwargs):
        """Create a queued directive bypassing post_save signal dispatch."""
        defaults = {"topic": topic, "payload": {}, "status": "queued"}
        defaults.update(kwargs)
        objs = Directive.objects.bulk_create([Directive(**defaults)])
        return objs[0]

    def test_process_directives_runs_registered_handler(self) -> None:
        directive = self._create_queued()

        call_command("process_directives")

        directive.refresh_from_db()
        self.assertEqual(directive.status, "done")
        self.assertEqual(self.handler.calls, 1)

    def test_process_directives_handles_unknown_topic(self) -> None:
        # Não explode mesmo sem handler (útil para debugging via --topic)
        self._create_queued(topic="unknown")

        call_command("process_directives", "--topic", "unknown")

        self.assertEqual(Directive.objects.filter(topic="unknown", status="queued").count(), 1)

    def test_process_directives_with_no_handlers_registered(self) -> None:
        """Should show warning when no handlers registered."""
        registry.clear()

        # Should not raise
        call_command("process_directives")

    def test_process_directives_with_limit(self) -> None:
        """Should respect --limit argument."""
        self._create_queued()
        self._create_queued()
        self._create_queued()

        call_command("process_directives", "--limit", "2")

        # Only 2 should be processed
        self.assertEqual(Directive.objects.filter(status="done").count(), 2)
        self.assertEqual(Directive.objects.filter(status="queued").count(), 1)

    def test_process_directives_with_specific_topic(self) -> None:
        """Should only process directives for specified topic."""
        self._create_queued()
        self._create_queued(topic="other.topic")

        call_command("process_directives", "--topic", self.handler.topic)

        self.assertEqual(Directive.objects.filter(topic=self.handler.topic, status="done").count(), 1)
        self.assertEqual(Directive.objects.filter(topic="other.topic", status="queued").count(), 1)

    def test_process_directives_no_directives_in_queue(self) -> None:
        """Should handle empty queue gracefully."""
        # No directives created
        call_command("process_directives")


class WindowedFailingHandler:
    """Handler com janela própria de retry, como fiscal e estorno."""

    topic = "windowed.topic"
    retry_delays_seconds = (30, 60, 120, 300, 600, 900, 1800)

    def __init__(self) -> None:
        self.terminal_calls: list[int] = []

    def handle(self, *, message: Directive, ctx: dict) -> None:
        raise RuntimeError("provedor fora do ar")

    def on_terminal_failure(self, *, message: Directive) -> None:
        self.terminal_calls.append(message.pk)


class ProcessDirectivesHonorsHandlerRetryWindowTests(TestCase):
    """O worker de produção segue a mesma régua do despacho inline."""

    def setUp(self) -> None:
        super().setUp()
        registry.clear()
        self.handler = WindowedFailingHandler()
        registry.register_directive_handler(self.handler)

    def tearDown(self) -> None:
        registry.clear()
        super().tearDown()

    def _queued(self, attempts: int) -> Directive:
        return Directive.objects.bulk_create(
            [Directive(topic="windowed.topic", payload={}, status="queued", attempts=attempts)]
        )[0]

    def test_fifth_failure_waits_the_handler_delay_instead_of_giving_up(self) -> None:
        from django.utils import timezone

        directive = self._queued(attempts=4)
        before = timezone.now()

        call_command("process_directives")

        directive.refresh_from_db()
        self.assertEqual(directive.status, "queued")
        self.assertEqual(directive.attempts, 5)
        self.assertGreaterEqual((directive.available_at - before).total_seconds(), 600)
        self.assertEqual(self.handler.terminal_calls, [])

    def test_exhausted_window_fails_and_calls_the_terminal_hook(self) -> None:
        directive = self._queued(attempts=7)

        call_command("process_directives")

        directive.refresh_from_db()
        self.assertEqual(directive.status, "failed")
        self.assertEqual(directive.attempts, 8)
        self.assertEqual(self.handler.terminal_calls, [directive.pk])

    def test_reaper_uses_the_handler_window_and_calls_the_terminal_hook(self) -> None:
        from datetime import timedelta

        from django.utils import timezone
        from shopman.orderman.management.commands.process_directives import _reap_stuck_directives

        stale = timezone.now() - timedelta(minutes=30)
        mid, last = Directive.objects.bulk_create([
            Directive(topic="windowed.topic", payload={}, status="running", attempts=5, started_at=stale),
            Directive(topic="windowed.topic", payload={}, status="running", attempts=8, started_at=stale),
        ])

        _reap_stuck_directives(timeout_minutes=10, max_attempts=5)

        mid.refresh_from_db()
        last.refresh_from_db()
        self.assertEqual(mid.status, "queued")
        self.assertEqual(last.status, "failed")
        self.assertEqual(self.handler.terminal_calls, [last.pk])
