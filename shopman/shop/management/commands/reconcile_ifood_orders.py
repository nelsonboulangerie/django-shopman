"""Aplica aos pedidos do iFood os fatos que já chegaram e ficaram esperando.

CFM, DSP e CON do iFood são gravados no pedido (``order.data["ifood"]``) mesmo
quando o pedido local ainda não chegou ao ponto; a aplicação acontecia só na
próxima transição local. Pedido em que ninguém mais mexe ficava parado para
sempre: o 3417 (12/11/2026) seguia "Em preparo" no Gestor quatro dias depois de
o iFood avisar que ele saiu e foi concluído.

Pedido de teste concluído no iFood fecha mesmo fora da janela (ver
``_stale_test_conclusion``). Roda no maintenance-worker. A regra é a mesma de sempre
(``ifood_events.reconcile_remote``): nunca inventa preparo, nunca pula a custódia
do entregador; só aplica o que os fatos já autorizam.
"""

from __future__ import annotations

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

#: Pedidos mais velhos que isto já não são da operação do dia.
LOOKBACK = timedelta(days=30)
#: Fato mais velho que isto não é aplicado sozinho: o pedido andaria agora e o
#: cliente receberia "saiu para entrega" horas depois de comer. Vira aviso, e
#: quem encerra é o operador.
APPLY_WINDOW = timedelta(hours=3)
ALERT_TYPE = "ifood_order_behind"


class Command(BaseCommand):
    help = "Aplica aos pedidos do iFood os fatos (confirmado, saiu, concluído) que ficaram esperando."

    def handle(self, *args, **options):
        from django.db.models import Q
        from shopman.orderman.models import Order

        from shopman.shop.services import ifood_events, ifood_ingest

        facts = Q()
        for marker in ("remote_confirmed", "remote_dispatched", "remote_concluded"):
            facts |= Q(**{f"data__ifood__{marker}__isnull": False})
        pending = (
            Order.objects.filter(channel_ref=ifood_ingest.IFOOD_CHANNEL_REF, created_at__gte=timezone.now() - LOOKBACK)
            .exclude(status__in=Order.TERMINAL_STATUSES)
            .filter(facts)
        )
        moved = 0
        now = timezone.now()
        for order in pending:
            if now - _latest_fact_at(order, default=now) > APPLY_WINDOW and not _stale_test_conclusion(order):
                _alert_behind(order)
                continue
            before = order.status
            ifood_events.reconcile_remote(order)
            order.refresh_from_db()
            if order.status != before:
                moved += 1
                self.stdout.write(f"reconcile_ifood_orders: {order.ref} {before} → {order.status}")
        if moved:
            self.stdout.write(f"reconcile_ifood_orders: {moved} pedido(s) alcançaram o iFood")


def _stale_test_conclusion(order) -> bool:
    """Pedido de TESTE que o iFood concluiu fecha aqui a qualquer tempo.

    A janela existe pelo cliente que receberia "saiu para entrega" horas depois
    de comer; pedido de teste não avisa ninguém, não emite nota nem mexe em
    estoque (``is_test_order``). É assim que os presos de antes da regra saem da
    fila, no próximo ciclo depois do deploy, e de novo sem efeito se já saíram.
    """
    from shopman.shop.services.order_helpers import is_test_order

    return is_test_order(order) and bool(((order.data or {}).get("ifood") or {}).get("remote_concluded"))


def _latest_fact_at(order, *, default):
    from django.utils.dateparse import parse_datetime

    facts = (order.data or {}).get("ifood") or {}
    seen = [
        parse_datetime(str((facts.get(marker) or {}).get("observed_at") or ""))
        for marker in ("remote_confirmed", "remote_dispatched", "remote_concluded")
    ]
    seen = [moment for moment in seen if moment is not None]
    return max(seen) if seen else default


def _alert_behind(order) -> None:
    from shopman.shop.services.observability import create_operator_alert

    facts = (order.data or {}).get("ifood") or {}
    if facts.get("remote_concluded"):
        there = "o iFood já concluiu"
    elif facts.get("remote_dispatched"):
        there = "o entregador do iFood já retirou"
    else:
        there = "o iFood já confirmou"
    display = str(facts.get("display_id") or "").strip()
    name = f"{order.ref} (iFood #{display})" if display else order.ref
    create_operator_alert(
        type=ALERT_TYPE,
        severity="warning",
        message=(
            f"O pedido {name} está \"{order.get_status_display()}\" aqui, mas {there}. "
            "Encerre o pedido aqui para a fila bater com o iFood."
        ),
        order_ref=order.ref,
        dedupe_key=f"{ALERT_TYPE}:{order.ref}",
        debounce_minutes=24 * 60,
    )
