"""Maquininha fora da loja além do tempo vira alerta para o Gestor.

A maquininha não tem indicador fixo na tela: enquanto está na rua, o card da
saída basta. Passou do limite (``Shop.defaults["delivery"]["card_machine_alert_minutes"]``,
default 120 min; 0 desliga), o Gestor recebe "Maquininha fora há 2 h: pedido 0415".
Um alerta por pedido: o dedupe segura enquanto o alerta não for resolvido.
"""

from __future__ import annotations

from datetime import datetime

from django.core.management.base import BaseCommand
from django.utils import timezone


def _hours_label(minutes: int) -> str:
    if minutes < 60:
        return f"{minutes} min"
    hours, rest = divmod(minutes, 60)
    return f"{hours} h" if not rest else f"{hours} h {rest} min"


class Command(BaseCommand):
    help = "Alerta quando uma maquininha está na rua há mais tempo que o limite."

    def handle(self, *args, **options):
        from shopman.shop.models import Shop
        from shopman.shop.services import operator_orders
        from shopman.shop.services.observability import create_operator_alert
        from shopman.shop.services.order_helpers import card_machine_alert_minutes

        limit = card_machine_alert_minutes(Shop.load())
        if limit <= 0:
            return
        now = timezone.now()
        seen: set[str] = set()
        for _ref, order in operator_orders.equipment_out():
            if order.ref in seen:
                continue
            seen.add(order.ref)
            custody = operator_orders.equipment_custody(order)
            try:
                out_at = datetime.fromisoformat(custody.out_at)
            except (TypeError, ValueError):
                continue
            if timezone.is_naive(out_at):
                out_at = timezone.make_aware(out_at)
            minutes = int((now - out_at).total_seconds() // 60)
            if minutes < limit:
                continue
            phrase = operator_orders.machine_phrase(((order.data or {}).get("dispatch") or {}).get("device_label") or "")
            create_operator_alert(
                type="card_machine_overdue",
                severity="warning",
                message=f"{phrase[0].upper() + phrase[1:]} fora há {_hours_label(minutes)}: pedido {operator_orders.short_ref(order.ref)}",
                order_ref=order.ref,
                # Chave que já está na frase: o dedupe não pendura "Dedupe: ..." no texto do alerta.
                dedupe_key=f"pedido {operator_orders.short_ref(order.ref)}",
            )
