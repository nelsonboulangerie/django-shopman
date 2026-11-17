"""B.I. — os dois tempos da encomenda na Cozinha, por pedido (decisão do dono, 09/11/2026).

Espera na Cozinha: ``kitchen_released_at`` até o "Iniciar" (``preparing_at``).
Preparo: "Iniciar" até o "Pronto" (``ready_at``). Venda do dia, sem carimbo,
fica fora (não vira zero).
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.contrib.auth.models import Permission, User
from django.urls import reverse
from django.utils import timezone
from shopman.orderman.models import Order

from shopman.backstage.projections.bi_preorder_kitchen import build_bi_preorder_kitchen

pytestmark = pytest.mark.django_db


def _order(ref, *, released=None, started=None, ready=None, status="accepted", created=None):
    data = {"is_preorder": True, "kitchen_released_at": released.isoformat()} if released else {}
    order = Order.objects.create(ref=ref, channel_ref="web", status=status, total_q=5000, data=data)
    # Os carimbos de transição vêm do status; aqui são fixados para medir a conta.
    stamps = {"preparing_at": started, "ready_at": ready}
    if created is not None:
        stamps["created_at"] = created
    Order.objects.filter(pk=order.pk).update(**stamps)
    return order


def test_preorder_with_both_times_and_one_still_waiting_for_start():
    base = timezone.now().replace(microsecond=0) - timedelta(hours=3)
    _order("NB-ENC1", released=base, started=base + timedelta(minutes=12), ready=base + timedelta(minutes=40),
        status="ready")
    _order("NB-ENC2", released=base + timedelta(minutes=30), started=base + timedelta(minutes=38),
        ready=base + timedelta(minutes=58), status="ready")
    # Chegou à Cozinha e ainda não teve o "Iniciar": aparece, sem os tempos.
    _order("NB-ENC3", released=base + timedelta(hours=1))

    report = build_bi_preorder_kitchen()

    assert (report.orders, report.started, report.ready) == (3, 2, 2)
    by_ref = {row.ref: row for row in report.rows}
    assert (by_ref["NB-ENC1"].wait_minutes, by_ref["NB-ENC1"].prep_minutes) == (12.0, 28.0)
    assert (by_ref["NB-ENC2"].wait_minutes, by_ref["NB-ENC2"].prep_minutes) == (8.0, 20.0)
    waiting = by_ref["NB-ENC3"]
    assert (waiting.started_at, waiting.ready_at, waiting.wait_minutes, waiting.prep_minutes) == (None, None, None, None)
    # As medianas só contam o que foi medido: a encomenda sem "Iniciar" não vira zero.
    assert report.wait_median_minutes == 10.0
    assert report.prep_median_minutes == 24.0
    # A chegada mais recente primeiro.
    assert [row.ref for row in report.rows] == ["NB-ENC3", "NB-ENC2", "NB-ENC1"]


def test_same_day_sale_and_cancelled_preorder_stay_out():
    base = timezone.now().replace(microsecond=0) - timedelta(hours=2)
    # Venda do dia: foi à Cozinha no aceite, sem carimbo de encomenda.
    _order("NB-DIA", started=base, ready=base + timedelta(minutes=15), status="ready")
    _order("NB-CANC", released=base, status="cancelled")

    report = build_bi_preorder_kitchen()

    assert report.orders == 0
    assert report.rows == ()
    assert (report.wait_median_minutes, report.prep_median_minutes) == (None, None)


def test_released_before_the_window_stays_out():
    old = timezone.now() - timedelta(days=40)
    _order("NB-VELHA", released=old, started=old + timedelta(minutes=5), ready=old + timedelta(minutes=30),
        created=old - timedelta(days=3))

    assert build_bi_preorder_kitchen().orders == 0
    since = timezone.localdate(old)
    assert build_bi_preorder_kitchen(date_from=since, date_to=since).orders == 1


def test_endpoint_serves_the_reading(client):
    base = timezone.now().replace(microsecond=0) - timedelta(hours=1)
    _order("NB-API", released=base, started=base + timedelta(minutes=5))
    user = User.objects.create_user("gestor-bi", password="x", is_staff=True)
    user.user_permissions.add(Permission.objects.get(codename="view_bi"))
    client.force_login(user)
    response = client.get(reverse("api-backstage-bi-preorder-kitchen"))

    assert response.status_code == 200
    body = response.json()["bi"]
    assert body["orders"] == 1
    assert body["rows"][0]["ref"] == "NB-API"
    assert body["rows"][0]["wait_minutes"] == 5.0
    assert body["rows"][0]["prep_minutes"] is None
