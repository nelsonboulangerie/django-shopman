"""Saúde da fila de directives — a observabilidade mínima exigida pela ADR-003.

Sem dead-letter queue, uma directive `failed` silencia; sob carga, backlog
`queued` cresce invisível; um worker morto ninguém percebe. Este check roda no
ciclo do maintenance_worker e vira OperatorAlert (debounce 15min) quando:

  * failed spike   — N+ directives falharam na janela recente;
  * backlog        — N+ directives `queued` vencidas há mais de X min
                     (nem o dispatch por signal nem o worker processaram);
  * worker parado  — heartbeat do process_directives sem ciclo há X min
                     (só alerta com batimento CONHECIDO envelhecido; ausência
                     de chave é "desconhecido" — em dev/CI o cache locmem é
                     por processo e o batimento de outro processo é invisível).

Os dois alertas que falam DA fila (backlog e worker parado) saem por e-mail
SÍNCRONO, aqui mesmo (``critical_alerts.deliver_now``): o aviso de que o worker
parou não pode depender do worker para sair. O debounce é o mesmo do alerta e
do e-mail; o e-mail que falhou de forma transitória é retentado no ciclo
seguinte (``critical_alerts.deliver_pending``). O failed spike e os demais
alertas seguem o caminho de sempre (Directive pela fila).

Thresholds via settings (defaults na ADR): SHOPMAN_DIRECTIVE_FAILED_ALERT_THRESHOLD,
SHOPMAN_DIRECTIVE_FAILED_WINDOW_MINUTES, SHOPMAN_DIRECTIVE_BACKLOG_ALERT_THRESHOLD,
SHOPMAN_DIRECTIVE_BACKLOG_AGE_MINUTES, SHOPMAN_WORKER_HEARTBEAT_STALE_MINUTES.

Uso:
    python manage.py check_directive_health
"""

from __future__ import annotations

import logging
from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

logger = logging.getLogger(__name__)

def _tasks(count: int) -> str:
    """Contagem na língua do operador: tarefa de fundo, nunca "directive(s)"."""
    return "1 tarefa de fundo" if count == 1 else f"{count} tarefas de fundo"


#: Alertas cujo e-mail não pode esperar a fila de directives.
QUEUE_HEALTH_ALERT_TYPES = ("directive_backlog", "directive_worker_stale")


class Command(BaseCommand):
    help = "Checa saúde da fila de directives (failed, backlog, heartbeat) e alerta o operador."

    def handle(self, *args, **options):
        from shopman.orderman.models import Directive

        from shopman.shop.services.observability import operational_event

        now = timezone.now()

        failed_threshold = int(getattr(settings, "SHOPMAN_DIRECTIVE_FAILED_ALERT_THRESHOLD", 5))
        failed_window = int(getattr(settings, "SHOPMAN_DIRECTIVE_FAILED_WINDOW_MINUTES", 60))
        backlog_threshold = int(getattr(settings, "SHOPMAN_DIRECTIVE_BACKLOG_ALERT_THRESHOLD", 5))
        backlog_age = int(getattr(settings, "SHOPMAN_DIRECTIVE_BACKLOG_AGE_MINUTES", 10))
        heartbeat_stale = int(getattr(settings, "SHOPMAN_WORKER_HEARTBEAT_STALE_MINUTES", 15))

        failed_recent = Directive.objects.filter(
            status="failed",
            updated_at__gte=now - timedelta(minutes=max(1, failed_window)),
        ).count()

        backlog_overdue = Directive.objects.filter(
            status="queued",
            available_at__lt=now - timedelta(minutes=max(1, backlog_age)),
        ).count()

        operational_event(
            "directive_health.checked",
            failed_recent=failed_recent,
            backlog_overdue=backlog_overdue,
        )

        if failed_recent >= max(1, failed_threshold):
            self._alert_failed_spike(failed_recent, failed_window)

        if backlog_overdue >= max(1, backlog_threshold):
            self._alert_backlog(backlog_overdue, backlog_age)

        self._check_worker_heartbeat(now, heartbeat_stale)

        from shopman.shop.services import critical_alerts

        try:
            critical_alerts.deliver_pending(QUEUE_HEALTH_ALERT_TYPES)
        except Exception:
            logger.exception("directive_health.deliver_pending_failed")

        self.stdout.write(
            f"directive_health: failed_recent={failed_recent} backlog_overdue={backlog_overdue}"
        )

    def _alert_failed_spike(self, count: int, window_minutes: int) -> None:
        from shopman.shop.services.observability import create_operator_alert

        create_operator_alert(
            type="directive_failed_spike",
            severity="error",
            message=(
                f"{_tasks(count)} falharam de vez nos últimos {window_minutes} min e não "
                "vão ser tentadas de novo sozinhas. Avisos ao cliente, nota fiscal ou "
                "estoque podem ter ficado para trás. Avise a TI para conferir e reprocessar."
            ),
            dedupe_key="directive_failed_spike",
        )

    def _alert_backlog(self, count: int, age_minutes: int) -> None:
        from shopman.shop.services.observability import create_operator_alert

        alert = create_operator_alert(
            type="directive_backlog",
            severity="error",
            message=(
                f"{_tasks(count)} esperam há mais de {age_minutes} min para rodar. O "
                "processo que executa essas tarefas pode estar parado ou sobrecarregado, "
                "e avisos ao cliente, nota fiscal e estoque atrasam com ele. Avise a TI."
            ),
            dedupe_key="directive_backlog",
        )
        self._page_now(alert)

    def _check_worker_heartbeat(self, now, stale_minutes: int) -> None:
        from shopman.orderman import worker_heartbeat

        from shopman.shop.services.observability import create_operator_alert

        last = worker_heartbeat.last_beat(worker_heartbeat.PROCESS_DIRECTIVES_WORKER)
        if last is None:
            logger.info(
                "directive_health: heartbeat do process_directives desconhecido "
                "(worker nunca visto por este cache) — sem alerta."
            )
            return

        age = now - last
        if age < timedelta(minutes=max(1, stale_minutes)):
            return

        alert = create_operator_alert(
            type="directive_worker_stale",
            severity="critical",
            message=(
                "O processo que executa as tarefas de fundo não termina uma rodada há "
                f"{int(age.total_seconds() // 60)} min. Avisos ao cliente, nota fiscal e "
                "estoque esperam por ele. Avise a TI."
            ),
            dedupe_key="directive_worker_stale:process_directives",
        )
        self._page_now(alert)

    def _page_now(self, alert) -> None:
        """E-mail do alerta da fila, enviado aqui e não pela fila."""
        if alert is None:  # debounced: o e-mail da janela já saiu (ou está saindo)
            return
        from shopman.shop.services import critical_alerts

        try:
            critical_alerts.deliver_now(alert)
        except Exception:
            # O alerta já está na tela; o e-mail que não saiu grita no log.
            logger.exception("directive_health.page_now_failed: %s", alert.type)
