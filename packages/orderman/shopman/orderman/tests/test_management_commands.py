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


# ── Reaper × worker: o desfecho só é gravado por quem ainda tem o claim ──────


class ReapedMidRunHandler:
    """Simula o reaper (ou outro worker) tomando a diretiva durante o handle."""

    topic = "reaped.topic"

    def __init__(self) -> None:
        self.calls: list[int] = []
        self.reap_pks: list[int] | None = None  # None = a própria diretiva
        self.reclaim = False
        self.raise_exc: BaseException | None = None
        self.terminal_calls: list[int] = []

    def handle(self, *, message: Directive, ctx: dict) -> None:
        from datetime import timedelta

        from django.db.models import F
        from django.utils import timezone
        from shopman.orderman.management.commands.process_directives import _reap_stuck_directives

        self.calls.append(message.pk)
        targets = [message.pk] if self.reap_pks is None else self.reap_pks
        Directive.objects.filter(pk__in=targets).update(
            started_at=timezone.now() - timedelta(minutes=30)
        )
        _reap_stuck_directives(timeout_minutes=10, max_attempts=5)
        if self.reclaim:
            # Outro processo reivindica a diretiva recolocada na fila.
            Directive.objects.filter(pk__in=targets).update(
                status="running", attempts=F("attempts") + 1, started_at=timezone.now()
            )
        if self.raise_exc is not None:
            raise self.raise_exc

    def on_terminal_failure(self, *, message: Directive) -> None:
        self.terminal_calls.append(message.pk)


class ProcessDirectivesClaimCompareAndSetTests(TestCase):
    """P2 do laudo de pedido/estoque (23/10): o reaper fazia a diretiva rodar duas vezes.

    O worker antigo, ao terminar depois do reaper, marcava `done` a execução de outro
    (ou devolvia à fila o que já tinha sido recolocado). O desfecho agora é um
    compare-and-set na ficha `(attempts, started_at)` do claim.
    """

    def setUp(self) -> None:
        super().setUp()
        registry.clear()
        self.handler = ReapedMidRunHandler()
        registry.register_directive_handler(self.handler)

    def tearDown(self) -> None:
        registry.clear()
        super().tearDown()

    def _queued(self, **kwargs) -> Directive:
        defaults = {"topic": "reaped.topic", "payload": {}, "status": "queued"}
        defaults.update(kwargs)
        return Directive.objects.bulk_create([Directive(**defaults)])[0]

    def test_reaper_revokes_the_claim(self) -> None:
        directive = self._queued()

        call_command("process_directives")

        directive.refresh_from_db()
        self.assertEqual(directive.status, "queued")
        self.assertIsNone(directive.started_at)
        self.assertIn("reaped", directive.last_error)

    def test_old_worker_does_not_mark_done_a_directive_reaped_mid_run(self) -> None:
        directive = self._queued()

        call_command("process_directives")

        directive.refresh_from_db()
        # Ficou como o reaper deixou: na fila, para UMA nova execução.
        self.assertEqual(directive.status, "queued")
        self.assertEqual(directive.attempts, 1)
        self.assertEqual(self.handler.calls, [directive.pk])

    def test_old_worker_does_not_finish_the_run_of_the_worker_that_reclaimed(self) -> None:
        self.handler.reclaim = True
        directive = self._queued()

        call_command("process_directives")

        directive.refresh_from_db()
        # A execução do outro processo segue dele: nem `done` nem devolvida à fila.
        self.assertEqual(directive.status, "running")
        self.assertEqual(directive.attempts, 2)

    def test_old_worker_failure_does_not_overwrite_the_reaper(self) -> None:
        self.handler.raise_exc = RuntimeError("timeout do provedor")
        directive = self._queued(attempts=1)

        call_command("process_directives")

        directive.refresh_from_db()
        # Sem o CAS, o worker antigo regravaria `transient` com o backoff dele.
        self.assertEqual(directive.status, "queued")
        self.assertEqual(directive.error_code, "")
        self.assertIn("reaped", directive.last_error)
        self.assertEqual(self.handler.terminal_calls, [])

    def test_directive_reaped_while_waiting_in_the_batch_is_skipped(self) -> None:
        first, second = self._queued(), self._queued()
        self.handler.reap_pks = [second.pk]

        call_command("process_directives")

        # A segunda foi tomada pelo reaper enquanto a primeira rodava: o worker
        # antigo não a executa (quem a roda é o próximo claim).
        self.assertEqual(self.handler.calls, [first.pk])
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(first.status, "done")
        self.assertEqual(second.status, "queued")

    def test_unrelated_success_still_completes(self) -> None:
        registry.clear()
        handler = DummyDirectiveHandler()
        registry.register_directive_handler(handler)
        directive = self._queued(topic="dummy.topic")

        call_command("process_directives")

        directive.refresh_from_db()
        self.assertEqual(directive.status, "done")
        self.assertEqual(directive.error_code, "")


# ── Watchdog: processo pendurado morre para a plataforma reiniciar ───────────


class WatchdogTests(TestCase):
    """O5 do laudo (23/10): worker pendurado (sem cair) não se recuperava."""

    def _watchdog(self, exits):
        from shopman.orderman.management.commands.process_directives import Watchdog

        return Watchdog("teste", poll_seconds=0.01, exit_func=exits.append)

    def test_expired_deadline_exits_with_nonzero_code(self) -> None:
        import time

        from shopman.orderman.management.commands.process_directives import WATCHDOG_EXIT_CODE

        exits: list[int] = []
        watchdog = self._watchdog(exits)
        watchdog.feed(0.05)
        watchdog.start()
        try:
            deadline = time.monotonic() + 2.0
            while not exits and time.monotonic() < deadline:
                time.sleep(0.01)
        finally:
            watchdog.stop()
        self.assertEqual(exits, [WATCHDOG_EXIT_CODE])
        self.assertNotEqual(WATCHDOG_EXIT_CODE, 0)

    def test_fed_watchdog_stays_quiet(self) -> None:
        import time

        exits: list[int] = []
        watchdog = self._watchdog(exits)
        watchdog.feed(0.3)
        watchdog.start()
        try:
            for _ in range(10):
                watchdog.feed(0.3)
                time.sleep(0.03)
        finally:
            watchdog.stop()
        self.assertEqual(exits, [])

    def test_hung_main_thread_process_is_killed(self) -> None:
        """Prova real: o processo com a thread principal presa sai sozinho, com código ≠ 0."""
        import os
        import subprocess
        import sys
        import textwrap

        from shopman.orderman.management.commands.process_directives import WATCHDOG_EXIT_CODE

        script = textwrap.dedent(
            """
            import time
            import django
            django.setup()
            from shopman.orderman.management.commands.process_directives import Watchdog
            watchdog = Watchdog("pendurado", poll_seconds=0.05)
            watchdog.feed(0.2)
            watchdog.start()
            time.sleep(60)  # a thread principal nunca mais dá sinal de vida
            """
        )
        env = {**os.environ, "PYTHONPATH": os.pathsep.join(p for p in sys.path if p)}
        result = subprocess.run(
            [sys.executable, "-c", script], env=env, capture_output=True, timeout=45,
        )
        self.assertEqual(result.returncode, WATCHDOG_EXIT_CODE, result.stderr.decode()[-2000:])

    def test_watch_mode_starts_and_stops_the_watchdog(self) -> None:
        from unittest.mock import patch

        registry.clear()
        registry.register_directive_handler(DummyDirectiveHandler())
        module = "shopman.orderman.management.commands.process_directives"
        try:
            with (
                patch(f"{module}.Watchdog") as watchdog_cls,
                patch(f"{module}.time.sleep", side_effect=KeyboardInterrupt),
                self.assertRaises(KeyboardInterrupt),
            ):
                call_command("process_directives", "--watch", "--watchdog-seconds", "90")
        finally:
            registry.clear()

        instance = watchdog_cls.return_value.start.return_value
        instance.feed.assert_called_with(90)
        instance.stop.assert_called_once()
