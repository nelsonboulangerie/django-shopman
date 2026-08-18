"""Worker de manutenção periódica — os "crons" do deployment.

O DigitalOcean App Platform não tem cron nativo; este worker roda o ciclo de
manutenção num loop (default: a cada 5 minutos):

  release_expired_holds     — holds vencidos saem do caminho (higiene)
  cleanup_stale_sessions    — sessões abandonadas antigas (liberando os holds delas)
  sweep_orphan_holds        — holds indefinidos órfãos (sem sessão viva/data passada)
  cleanup_stale_planning    — quants planejados órfãos
  expire_stale_announcements    — announcement pendente sem aprovação a tempo caduca
  dispatch_due_announcements — announcement aprovado com hora marcada sai quando chega a hora
  arm_scheduled_campaigns    — ARMA (não dispara) as ocasiões agendadas do próximo horizonte
  reconcile_payments        — PIX pago com webhook perdido é resgatado
  sweep_stuck_orders        — fase de lifecycle perdida (crash pós-commit) é re-despachada
  sweep_unrealized_production — fornada concluída sem o ledger de estoque fechado é re-realizada
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
    # Logo depois de liberar reservas: reserva que expira sai por update em
    # massa, sem signal, então é aqui que a volta do produto é percebida.
    "reconcile_shelf_outages",
    # O expediente do dia que terminou vira denominador congelado: sem isso,
    # mexer no horário da loja reescreveria as métricas do passado.
    "stamp_business_days",
    # Depende do expediente carimbado acima: é ele que diz quando a casa
    # estava aberta, e só dentro disso um silêncio de vendas é episódio.
    "detect_operation_episodes",
    # Timer de forno sem Concluir dentro do teto não mede (ADR-021 §4).
    "sweep_stale_oven_runs",
    # Frescor vencido não vira propaganda: announcement pendente além do prazo caduca.
    "expire_stale_announcements",
    # Aprovado com hora marcada sai sozinho quando o relógio chega.
    "dispatch_due_announcements",
    "arm_scheduled_campaigns",
    "reconcile_payments",
    "sweep_stuck_orders",
    # O mesmo resgate, do lado da produção: fornada concluída cujo ledger de
    # estoque não fechou (queda no meio do handler) volta a ser realizada.
    "sweep_unrealized_production",
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
            started = time.monotonic()
            try:
                self._run_cycle()
            except Exception:
                logger.exception("maintenance_worker: ciclo falhou (worker continua)")
            if once:
                return

            # Dormir o que RESTA do intervalo, não o intervalo inteiro. Antes, "a cada
            # 5 minutos" era falso para todos os crons daqui: o período real era
            # `interval + duração do ciclo`, e a duração cresce com a base. Um ciclo de
            # 90s virava um período de 6min30 sem ninguém notar — e a deriva se acumula.
            elapsed = time.monotonic() - started
            remaining = interval - elapsed
            if remaining > 0:
                time.sleep(remaining)
            else:
                # Ciclo mais lento que o intervalo: não dormir nada, e dizer. Silêncio
                # aqui esconderia que a manutenção não está dando conta.
                logger.warning(
                    "maintenance_worker: ciclo levou %.1fs, mais que o intervalo de %ds",
                    elapsed, interval,
                )

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
