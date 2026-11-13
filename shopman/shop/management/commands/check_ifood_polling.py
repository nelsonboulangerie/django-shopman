"""Confere o sinal de vida do polling do iFood e alerta quando ele para.

Roda no ciclo do maintenance-worker. Lê a hora do último poll que o iFood
respondeu (``ifood_poll_health``) e, passados 2 minutos, cria um
``OperatorAlert`` crítico (``ifood_poll_stale``): sem polling, pedido novo do
iFood não entra e o iFood o cancela em 8 minutos sem aceite. O e-mail sai aqui
mesmo (``critical_alerts.deliver_now``), sem depender da fila de directives.
Quando o polling volta a responder, o alerta aberto é resolvido.

Integração direta não configurada, ou cache por processo (dev/CI): volta calado.

Uso:
    python manage.py check_ifood_polling
"""

from __future__ import annotations

import logging

from django.core.management.base import BaseCommand
from django.utils import timezone

logger = logging.getLogger(__name__)

ALERT_TYPE = "ifood_poll_stale"
#: Trecho fixo da mensagem: é por ele que o alerta aberto é resolvido.
MESSAGE_MARKER = "Os pedidos do iFood pararam de entrar no sistema"
RESOLVED_BY = "check_ifood_polling"


def _message(health) -> str:
    if health.last_success is None:
        when = "nenhuma leitura do iFood foi registrada"
    else:
        local = timezone.localtime(health.last_success)
        minutes = max(1, (health.age_seconds or 0) // 60)
        when = f"a última leitura do iFood foi às {local:%H:%M} (há {minutes} min)"
    return (
        f"{MESSAGE_MARKER}: {when}. O iFood cancela o pedido que não for aceito em "
        "8 minutos. Enquanto isso, aceite os pedidos novos pelo Portal do Parceiro "
        "do iFood e avise a TI."
    )


class Command(BaseCommand):
    help = "Alerta quando o polling do iFood passa de 2 minutos sem resposta."

    def handle(self, *args, **options):
        from shopman.shop.services import ifood_poll_health as poll_health

        health = poll_health.current()
        if health.state in {poll_health.DISABLED, poll_health.UNKNOWN}:
            return
        if not health.failing:
            self._resolve_open()
            return

        from shopman.shop.services.observability import create_operator_alert

        alert = create_operator_alert(
            type=ALERT_TYPE,
            severity="critical",
            message=_message(health),
            dedupe_key=MESSAGE_MARKER,
            age_seconds=health.age_seconds,
        )
        self.stdout.write(f"check_ifood_polling: {health.state} age={health.age_seconds}")
        self._page_now(alert)

    def _resolve_open(self) -> None:
        from shopman.shop.adapters import alert as alert_adapter

        resolved = alert_adapter.resolve_matching(
            ALERT_TYPE, message_contains=MESSAGE_MARKER, actor=RESOLVED_BY
        )
        if resolved:
            self.stdout.write(f"check_ifood_polling: polling voltou, {resolved} alerta(s) resolvido(s)")

    def _page_now(self, alert) -> None:
        if alert is None:  # debounce: o e-mail da janela já saiu
            return
        from shopman.shop.services import critical_alerts

        try:
            critical_alerts.deliver_now(alert)
        except Exception:
            logger.exception("check_ifood_polling.page_now_failed")
