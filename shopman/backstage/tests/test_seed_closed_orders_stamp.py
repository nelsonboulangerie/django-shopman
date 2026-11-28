"""O pedido que o seed cria fechado leva o carimbo do fechamento (beta 05/11, ge:BI-03).

Sem ``completed_at`` o Histórico do Gestor, que conta pelo fechamento, caía no
``updated_at`` e jogava a venda de ontem para hoje: o "Abrir os 35 pedidos" do
B.I. abria a lista vazia.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta

import pytest
from django.utils import timezone
from shopman.orderman.models import Order

from config.management.commands.seed import Command

pytestmark = pytest.mark.django_db


def test_stamp_closed_orders_dates_completed_and_cancelled_by_the_order_time():
    made = timezone.make_aware(datetime.combine(timezone.localdate() - timedelta(days=1), time(10, 0)))
    done = Order.objects.create(ref="SEED-DONE", channel_ref="web", status="completed", total_q=1000)
    gone = Order.objects.create(ref="SEED-GONE", channel_ref="web", status="cancelled", total_q=1000)
    live = Order.objects.create(ref="SEED-LIVE", channel_ref="web", status="preparing", total_q=1000)
    Order.objects.filter(pk__in=[done.pk, gone.pk, live.pk]).update(
        created_at=made, completed_at=None, cancelled_at=None
    )

    assert Command()._stamp_closed_orders() == 2

    done.refresh_from_db()
    gone.refresh_from_db()
    live.refresh_from_db()
    assert done.completed_at == made + Command.SEED_CLOSE_AFTER
    assert gone.cancelled_at == made + Command.SEED_CLOSE_AFTER
    assert live.completed_at is None and live.cancelled_at is None
    # Idempotente: quem já tem carimbo não é tocado.
    assert Command()._stamp_closed_orders() == 0
