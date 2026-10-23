from __future__ import annotations

import logging
import os
import threading
import time
from collections.abc import Callable, Sequence
from datetime import datetime, timedelta
from time import monotonic as _monotonic

from django.core.management import BaseCommand
from django.db import close_old_connections, transaction
from django.utils import timezone
from shopman.orderman import registry, worker_heartbeat
from shopman.orderman.dispatch import notify_terminal_failure, retry_policy
from shopman.orderman.exceptions import DirectiveTerminalError, DirectiveTransientError
from shopman.orderman.models import Directive

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 5
REAP_STUCK_TIMEOUT_MINUTES = 10
#: Segundos sem sinal de vida até o watchdog encerrar o processo em ``--watch``.
#: Igual ao prazo do reaper de propósito: uma diretiva que roda mais que isso já é
#: considerada presa e será recolocada na fila; um processo que fica esse tempo
#: sem dar sinal está pendurado, e morrer é a única forma de a DO reiniciá-lo.
WATCHDOG_SECONDS = REAP_STUCK_TIMEOUT_MINUTES * 60
#: Código de saída do watchdog (EX_SOFTWARE). Diferente de 0 para a DO contar
#: como queda, reiniciar o componente e alimentar o alerta RESTART_COUNT.
WATCHDOG_EXIT_CODE = 70


class Watchdog:
    """Cão de guarda do processo: quem não dá sinal de vida no prazo morre.

    O laço do worker chama ``feed(segundos)`` antes de cada passo que pode
    demorar ("o próximo sinal vem em até N segundos"). Uma thread daemon só
    compara o relógio com esse prazo; vencido, loga e chama ``os._exit``. Não há
    nada a limpar, de propósito: o processo está pendurado (conexão presa, handler
    sem timeout), ``sys.exit`` numa thread não derrubaria o principal, e o que
    importa é a DO ver o componente cair e subir um novo. A diretiva que ficou
    ``running`` volta para a fila pelo reaper do processo novo.

    A thread não toca banco, cache nem nada que possa pendurar junto: lê um
    float. O relógio é o ``monotonic`` capturado na importação, para que um teste
    que troca ``time.monotonic`` não engane o watchdog.

    Também serve ao ``maintenance_worker`` (que já depende do orderman pelo
    heartbeat).
    """

    def __init__(
        self,
        name: str,
        *,
        poll_seconds: float = 5.0,
        exit_code: int = WATCHDOG_EXIT_CODE,
        exit_func: Callable[[int], None] = os._exit,
    ) -> None:
        self.name = name
        self.poll_seconds = poll_seconds
        self.exit_code = exit_code
        self._exit = exit_func
        self._deadline = _monotonic() + 3600.0
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def feed(self, within_seconds: float) -> None:
        """O próximo sinal de vida chega em até ``within_seconds``."""
        self._deadline = _monotonic() + max(float(within_seconds), 0.0)

    def start(self) -> Watchdog:
        if self._thread is None:
            self._thread = threading.Thread(
                target=self._run, name=f"watchdog:{self.name}", daemon=True
            )
            self._thread.start()
        return self

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=self.poll_seconds + 1.0)
            self._thread = None

    def _run(self) -> None:
        while not self._stop.wait(self.poll_seconds):
            late = _monotonic() - self._deadline
            if late > 0:
                logger.critical(
                    "watchdog: %s sem sinal de vida há %.0fs além do prazo; "
                    "encerrando o processo (código %d) para a plataforma reiniciar",
                    self.name, late, self.exit_code,
                )
                for handler in logging.getLogger().handlers:
                    try:
                        handler.flush()
                    except Exception:  # silêncio-deliberado: o critical já foi emitido; flush falho não pode impedir a saída
                        pass
                self._exit(self.exit_code)
                return


def _reap_stuck_directives(timeout_minutes: int, max_attempts: int) -> int:
    """
    Reset directives stuck in "running" back to "queued" for retry.

    A directive is considered stuck if:
    - status == "running"
    - started_at is older than timeout_minutes ago

    This covers the case where a worker crashes (OOM, deploy, power failure)
    between marking a directive as "running" and completing processing.

    O reaper REVOGA o claim: ``started_at`` volta a ``None``. O worker que
    reivindicou a diretiva guarda ``(attempts, started_at)`` como ficha e só
    escreve o desfecho se a ficha ainda bater (ver ``_claim_matches``). Sem isso,
    um worker lento (ou um segundo processo num deploy sobreposto) que terminasse
    depois do reaper marcaria ``done`` a execução de outro, ou devolveria à fila
    uma diretiva que já tinha sido recolocada e reprocessada.

    Returns:
        Number of directives reaped.
    """
    cutoff = timezone.now() - timedelta(minutes=timeout_minutes)

    with transaction.atomic():
        stuck = (
            Directive.objects.select_for_update(skip_locked=True)
            .filter(status="running", started_at__lte=cutoff)
        )
        stuck_list = list(stuck)

        reaped = 0
        failed = []
        for d in stuck_list:
            handler_max_attempts, _ = retry_policy(
                registry.get_directive_handler(d.topic), d.attempts, max_attempts
            )
            if d.attempts >= handler_max_attempts:
                d.status = "failed"
                failed.append(d)
                d.last_error = f"Stuck in 'running' for >{timeout_minutes}min (reaped after {d.attempts} attempts)"
            else:
                d.status = "queued"
                d.available_at = timezone.now()
                d.last_error = f"Stuck in 'running' for >{timeout_minutes}min (reaped, will retry)"
            d.started_at = None
            d.save(update_fields=["status", "available_at", "last_error", "started_at", "updated_at"])
            reaped += 1

    for d in failed:
        notify_terminal_failure(registry.get_directive_handler(d.topic), d)
    return reaped


def _claim_matches(directive: Directive, attempts: int, started_at: datetime) -> bool:
    return directive.attempts == attempts and directive.started_at == started_at


def _restamp_claim(directive: Directive, attempts: int, started_at: datetime) -> datetime | None:
    """Carimba ``started_at`` desta diretiva no instante em que ela vai rodar.

    O lote é reivindicado de uma vez com o mesmo ``started_at``; a última do lote
    pode esperar minutos pela vez dela. Recarimbar por diretiva faz o prazo do
    reaper contar a execução, não a fila. É um compare-and-set: se o reaper (ou
    outro processo) já tomou a diretiva, nada é escrito e ela é pulada, porque não
    é mais deste worker.
    """
    stamp = timezone.now()
    updated = Directive.objects.filter(
        pk=directive.pk, status="running", attempts=attempts, started_at=started_at
    ).update(started_at=stamp, updated_at=stamp)
    if not updated:
        return None
    directive.started_at = stamp
    return stamp


def _save_if_claimed(
    directive: Directive,
    attempts: int,
    started_at: datetime,
    fields: dict,
    *,
    only_if_running: bool = False,
) -> bool:
    """Grava o desfecho só se o claim ainda for deste worker (compare-and-set).

    Lê a linha sob ``select_for_update`` e confere a ficha ``(attempts,
    started_at)``: o reaper zera ``started_at`` e um novo claim incrementa
    ``attempts``, então qualquer um dos dois faz a ficha divergir. Divergiu, não
    escreve nada e devolve ``False``. Usa ``save()`` (não ``update()``) para manter
    os signals do modelo.
    """
    with transaction.atomic():
        current = Directive.objects.select_for_update().filter(pk=directive.pk).first()
        if current is None or not _claim_matches(current, attempts, started_at):
            logger.warning(
                "Directive %s #%s: claim perdido (reaper ou outro worker); "
                "desfecho deste worker descartado",
                directive.topic, directive.pk,
            )
            return False
        if only_if_running and current.status != "running":
            fields = {k: v for k, v in fields.items() if k != "status"}
        for name, value in fields.items():
            setattr(current, name, value)
        current.save(update_fields=[*fields, "updated_at"])
    for name in ("status", "error_code", "last_error", "available_at", "attempts", "started_at"):
        setattr(directive, name, getattr(current, name))
    return True


class Command(BaseCommand):
    help = "Processa diretivas enfileiradas usando os handlers registrados."

    def add_arguments(self, parser):
        parser.add_argument(
            "--topic",
            action="append",
            dest="topics",
            default=None,
            help="Topic específico para processar (pode repetir a opção). Omitido = todos os registrados.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=50,
            help="Quantidade máxima de diretivas processadas nesta execução (default: 50).",
        )
        parser.add_argument(
            "--watch",
            action="store_true",
            help="Mantém o comando rodando em loop (worker simples).",
        )
        parser.add_argument(
            "--interval",
            type=float,
            default=2.0,
            help="Intervalo (segundos) entre execuções quando usado com --watch (default: 2s).",
        )
        parser.add_argument(
            "--max-attempts",
            type=int,
            default=MAX_ATTEMPTS,
            help=f"Número máximo de tentativas antes de marcar como failed (default: {MAX_ATTEMPTS}).",
        )
        parser.add_argument(
            "--reap-timeout",
            type=int,
            default=REAP_STUCK_TIMEOUT_MINUTES,
            help=(
                f"Minutos após os quais uma diretiva 'running' é considerada stuck "
                f"e resetada para retry (default: {REAP_STUCK_TIMEOUT_MINUTES}). "
                f"Use 0 para desabilitar."
            ),
        )
        parser.add_argument(
            "--watchdog-seconds",
            type=int,
            default=WATCHDOG_SECONDS,
            help=(
                f"Em --watch, segundos sem sinal de vida até o processo se encerrar "
                f"(código {WATCHDOG_EXIT_CODE}) para a plataforma reiniciá-lo "
                f"(default: {WATCHDOG_SECONDS}). Use 0 para desabilitar."
            ),
        )

    def handle(self, *args, **opts):
        # Heartbeat de arranque (ADR-003 — observabilidade mínima): registrar que
        # este worker rodou nesta invocação, independente de haver handlers ou
        # diretivas na fila. O batimento significa "o worker está vivo e executou",
        # não "havia trabalho"; sem isto, um worker rodando com registry vazio
        # pareceria "stale" para quem monitora. Em --watch o _cycle refresca a cada
        # ciclo; aqui garantimos o batimento mesmo no early-return de "sem handlers".
        worker_heartbeat.beat(worker_heartbeat.PROCESS_DIRECTIVES_WORKER)

        topics: Sequence[str] | None = opts.get("topics")
        if topics:
            topics = [t for t in topics if t]
        else:
            topics = sorted(registry.get_directive_handlers().keys())

        if not topics:
            self.stdout.write(self.style.WARNING("Nenhum handler registrado. Nada a fazer."))
            return

        limit = max(int(opts.get("limit") or 1), 1)
        watch = bool(opts.get("watch"))
        interval = max(float(opts.get("interval") or 1.0), 0.5)
        max_attempts = max(int(opts.get("max_attempts") or MAX_ATTEMPTS), 1)
        reap_timeout = max(int(opts.get("reap_timeout") or 0), 0)
        watchdog_seconds = max(int(opts.get("watchdog_seconds") or 0), 0)
        watchdog: Watchdog | None = None

        def _alive():
            if watchdog is not None:
                watchdog.feed(watchdog_seconds)

        def _reap():
            """Reap stuck directives before processing new ones."""
            if not reap_timeout:
                return
            reaped = _reap_stuck_directives(reap_timeout, max_attempts)
            if reaped:
                self.stdout.write(
                    self.style.WARNING(f"Reaper: {reaped} diretiva(s) stuck resetada(s).")
                )

        def _cycle():
            # Heartbeat por ciclo (ADR-003 — observabilidade mínima): quem
            # monitora sabe quando este worker rodou pela última vez.
            worker_heartbeat.beat(worker_heartbeat.PROCESS_DIRECTIVES_WORKER)
            now = timezone.now()

            # Acquire directives with row-level lock (skip_locked prevents duplicate processing)
            with transaction.atomic():
                qs = (
                    Directive.objects.select_for_update(skip_locked=True)
                    .filter(status="queued", topic__in=topics, available_at__lte=now)
                    .order_by("available_at", "id")
                )
                directives = list(qs[:limit])

                if not directives:
                    return False

                for d in directives:
                    d.status = "running"
                    d.attempts += 1
                    d.started_at = now
                    d.save(update_fields=["status", "attempts", "started_at", "updated_at"])

            # Process outside the lock transaction
            processed = 0
            failures = 0

            for directive in directives:
                attempts = directive.attempts
                handler = registry.get_directive_handler(directive.topic)
                if not handler:
                    self.stdout.write(
                        self.style.WARNING(f"Ignorando tópico {directive.topic}: nenhum handler registrado.")
                    )
                    _save_if_claimed(
                        directive, attempts, now, {"status": "queued", "attempts": attempts - 1},
                    )
                    continue

                # Ficha do claim, recarimbada no instante de rodar (o prazo do
                # reaper conta a execução, não a espera no lote). Se o claim já
                # não é deste worker, a diretiva é de outro: pula sem rodar.
                started_at = _restamp_claim(directive, attempts, now)
                if started_at is None:
                    logger.warning(
                        "Directive %s #%s: claim perdido antes de rodar; pulada",
                        directive.topic, directive.pk,
                    )
                    continue
                _alive()

                handler_max_attempts, retry_delay = retry_policy(handler, attempts, max_attempts)
                outcome: dict | None = None
                only_if_running = False
                try:
                    handler.handle(message=directive, ctx={"actor": "process_directives"})
                    # Auto-complete: only if handler didn't change status (e.g. deferral)
                    outcome = {"status": "done", "error_code": ""}
                    only_if_running = True
                    processed += 1
                except DirectiveTerminalError as exc:
                    logger.error(
                        "Directive %s #%s terminal failure (attempt %d): %s",
                        directive.topic, directive.pk, attempts, exc,
                    )
                    outcome = {"status": "failed", "error_code": "terminal", "last_error": str(exc)[:500]}
                    failures += 1
                    self.stderr.write(
                        self.style.ERROR(f"Terminal: {directive.topic} #{directive.pk}: {exc}")
                    )
                except DirectiveTransientError as exc:
                    logger.warning(
                        "Directive %s #%s transient failure (attempt %d/%d): %s",
                        directive.topic, directive.pk, attempts, handler_max_attempts, exc,
                    )
                    outcome = _retry_outcome(attempts, handler_max_attempts, now, retry_delay, exc)
                    failures += 1
                    self.stderr.write(
                        self.style.WARNING(f"Transient: {directive.topic} #{directive.pk}: {exc}")
                    )
                except Exception as exc:
                    logger.exception(
                        "Directive %s #%s failed (attempt %d/%d)",
                        directive.topic, directive.pk, attempts, handler_max_attempts,
                    )
                    outcome = _retry_outcome(attempts, handler_max_attempts, now, retry_delay, exc)
                    failures += 1
                    self.stderr.write(
                        self.style.ERROR(f"Erro ao processar {directive.topic} #{directive.pk}: {exc}")
                    )
                finally:
                    # Compare-and-set: o desfecho só é gravado se o claim ainda
                    # for deste worker. Recolocada na fila pelo reaper (ou já
                    # reivindicada por outro processo), a diretiva não é marcada
                    # `done` nem devolvida à fila por ele.
                    wrote = outcome is not None and _save_if_claimed(
                        directive, attempts, started_at, outcome, only_if_running=only_if_running,
                    )
                    if wrote and directive.status == "failed":
                        notify_terminal_failure(handler, directive)

            self.stdout.write(self.style.SUCCESS(f"Diretivas concluídas: {processed}"))
            if failures:
                self.stdout.write(self.style.ERROR(f"Diretivas com erro: {failures}"))
            return True

        # Single-run mode
        if not watch:
            _reap()
            _cycle()
            return

        # Watch mode
        self.stdout.write(self.style.WARNING("Worker iniciado: Ctrl+C para sair."))
        # Watchdog (O5 do laudo de 23/10): processo pendurado (sem cair) não se
        # recuperava, porque o reaper mora dentro dele e o heartbeat só
        # envelhecia. Agora cada ciclo e cada diretiva renovam o prazo; vencido, o
        # processo sai com código diferente de 0 e a DO reinicia o componente.
        if watchdog_seconds:
            watchdog = Watchdog(worker_heartbeat.PROCESS_DIRECTIVES_WORKER).start()
        cycle_count = 0
        try:
            while True:
                _alive()
                try:
                    # Higiene de conexão: sem fronteira de request num loop, o Django
                    # não recicla sozinho a conexão persistente do Postgres derrubada
                    # pelo pooler (PgBouncer) ou obsoleta por CONN_MAX_AGE. O loop é
                    # apertado (default 2s), mas um failover do banco reproduz o
                    # mesmo problema aqui — este close reconecta limpo no ciclo seguinte.
                    close_old_connections()
                    # Reap stuck directives every 5 cycles to avoid overhead
                    if cycle_count % 5 == 0:
                        _reap()
                    _cycle()
                except KeyboardInterrupt:
                    self.stdout.write(self.style.WARNING("Worker encerrado."))
                    break
                except Exception:
                    # Um ciclo NUNCA derruba o worker: loga e segue (o próximo
                    # reconecta). Sem isto o processo saía e a DO reiniciava (alerta
                    # RESTART_COUNT).
                    logger.exception("process_directives: ciclo falhou (worker continua)")
                cycle_count += 1
                _alive()
                time.sleep(interval)
        finally:
            if watchdog is not None:
                watchdog.stop()


def _retry_outcome(attempts: int, handler_max_attempts: int, now, retry_delay: int, exc) -> dict:
    if attempts >= handler_max_attempts:
        outcome = {"status": "failed", "error_code": "terminal"}
    else:
        outcome = {
            "status": "queued",
            "error_code": "transient",
            "available_at": now + timedelta(seconds=retry_delay),
        }
    outcome["last_error"] = str(exc)[:500]
    return outcome
