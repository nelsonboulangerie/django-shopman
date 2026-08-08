"""Worker de manutenção periódica — os "crons" do deployment.

O DigitalOcean App Platform não tem cron nativo; este worker roda o ciclo de
manutenção num loop (default: a cada 5 minutos):

  release_expired_holds     — holds vencidos saem do caminho (higiene)
  cleanup_stale_sessions    — sessões abandonadas antigas (liberando os holds delas)
  sweep_orphan_holds        — holds indefinidos órfãos (sem sessão viva/data passada)
  cleanup_stale_planning    — quants planejados órfãos
  cleanup_d1                — D-1 vencido vira perda
  expire_stale_announcements    — announcement pendente sem aprovação a tempo caduca
  dispatch_due_announcements — announcement aprovado com hora marcada sai quando chega a hora
  reconcile_payments        — PIX pago com webhook perdido é resgatado
  sweep_stuck_orders        — fase de lifecycle perdida (crash pós-commit) é re-despachada
  check_directive_health    — failed/backlog/heartbeat da fila viram OperatorAlert (ADR-003)

Cada tarefa é isolada: uma falha loga e NUNCA derruba o ciclo das demais.
Cada ciclo grava o heartbeat "maintenance_worker" (shopman.orderman.worker_heartbeat).

Uso:
    python manage.py maintenance_worker             # loop infinito (worker)
    python manage.py maintenance_worker --once      # um ciclo (debug/CI)
    python manage.py maintenance_worker --interval 60
"""

from __future__ import annotations

import logging
import time

from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import close_old_connections

logger = logging.getLogger(__name__)

MAINTENANCE_COMMANDS = (
    "release_expired_holds",
    "cleanup_stale_sessions",
    # Depois do cleanup (que já libera ao deletar) e antes do planning: holds
    # órfãos liberados aqui destravam quants planejados órfãos no mesmo ciclo.
    "sweep_orphan_holds",
    "cleanup_stale_planning",
    "cleanup_d1",
    # Frescor vencido não vira propaganda: announcement pendente além do prazo caduca.
    "expire_stale_announcements",
    # Aprovado com hora marcada sai sozinho quando o relógio chega.
    "dispatch_due_announcements",
    "reconcile_payments",
    "sweep_stuck_orders",
    # Por último: as checagens veem o estado PÓS-remediação do ciclo (menos flap).
    "check_directive_health",
)

MAINTENANCE_WORKER = "maintenance_worker"


class Command(BaseCommand):
    help = "Roda o ciclo de manutenção periódica (crons do deployment) em loop."

    def add_arguments(self, parser):
        parser.add_argument("--interval", type=int, default=300, help="Segundos entre ciclos (default 300).")
        parser.add_argument("--once", action="store_true", help="Roda um único ciclo e sai.")

    def handle(self, *args, **options):
        interval = max(30, int(options["interval"]))
        once = bool(options["once"])
        while True:
            # Um ciclo NUNCA derruba o worker. Durante o sleep ocioso (default 5
            # min) a conexão de banco/cache é reciclada pelo pooler; se a primeira
            # chamada do ciclo seguinte reaparecer como erro (ex.: o heartbeat no
            # Redis), logamos e seguimos — o próximo ciclo reconecta. Sem isto o
            # processo saía, a DO reiniciava, e o alerta RESTART_COUNT disparava.
            try:
                self._run_cycle()
            except Exception:
                logger.exception("maintenance_worker: ciclo falhou (worker continua)")
            if once:
                return
            time.sleep(interval)

    def _run_cycle(self) -> None:
        from shopman.orderman import worker_heartbeat

        # Higiene de conexão: um management command em loop não tem fronteira de
        # request, então o Django nunca recicla sozinho a conexão persistente do
        # Postgres. Após o sleep ela já passou do CONN_MAX_AGE e/ou foi derrubada
        # pelo pooler (PgBouncer). Sem este close, TODA query do ciclo falharia
        # até um restart — a manutenção viraria no-op silencioso.
        close_old_connections()
        worker_heartbeat.beat(MAINTENANCE_WORKER)
        for command in MAINTENANCE_COMMANDS:
            try:
                call_command(command)
            except Exception:
                logger.exception("maintenance_worker: %s falhou (ciclo continua)", command)
