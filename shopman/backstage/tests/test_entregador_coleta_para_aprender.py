"""A coleta que ensina a chamada antecipada do entregador (WP-ENTREGADOR-CHAMADA-ANTECIPADA).

O automático vem depois do go-live; o registro começa agora. Três lacunas fechadas:
o início do preparo no TICKET (vale para a comanda não paga), a carga da Cozinha
nesse instante, e a hora de cada letra da corrida (``status_at``). E a leitura do
B.I. que já devolve preparo real e chegada do entregador.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from django.contrib.auth.models import Permission, User
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse
from django.utils import timezone
from shopman.orderman.models import Order, OrderItem, Session

from shopman.backstage.models import DayClosing, KDSInstance, KDSTicket
from shopman.backstage.projections.bi_delivery_timing import build_bi_delivery_timing


@pytest.fixture
def station(db):
    return KDSInstance.objects.create(ref="prep-coleta", name="Preparo", type="prep", target_time_minutes=10)


def _order(ref, *, status=Order.Status.ACCEPTED, **fields):
    return Order.objects.create(
        ref=ref, channel_ref="web", session_key=f"sk-{ref}", status=status, total_q=1000,
        data={"customer": {"name": "Ana"}, "fulfillment_type": "delivery"}, **fields,
    )


@pytest.mark.django_db
def test_first_start_stamps_the_ticket_with_who_when_and_the_kitchen_load(station):
    from shopman.shop.services import kds

    order = _order("COL-1")
    ticket = KDSTicket.objects.create(session_key=order.session_key, kds_instance=station, items=[])
    # Carga: dois tickets abertos em outra venda, um concluído que não conta.
    other = KDSTicket.objects.create(session_key="sk-outra", kds_instance=station, items=[])
    KDSTicket.objects.create(session_key="sk-outra-2", kds_instance=station, items=[], status="in_progress")
    KDSTicket.objects.create(session_key="sk-feita", kds_instance=station, items=[], status="done")

    assert kds.start_ticket(ticket, actor="rafael")
    ticket.refresh_from_db()
    assert ticket.started_by == "rafael"
    assert ticket.started_at is not None
    assert ticket.open_tickets_at_start == 2
    first_at = ticket.started_at

    # O replay e um segundo início não sobrescrevem o marco.
    assert kds.start_ticket(ticket, actor="bia")
    ticket.refresh_from_db()
    assert (ticket.started_by, ticket.started_at) == ("rafael", first_at)
    assert other.pk  # a carga não mexeu nos outros


@pytest.mark.django_db
def test_unpaid_tab_ticket_records_the_start_without_an_order(station):
    """A comanda (Session) não tem ``Order.data``: o marco vive no ticket e sobrevive ao commit."""
    from shopman.shop.services import kds

    Session.objects.create(session_key="sk-comanda", channel_ref="pdv", state="open")
    ticket = KDSTicket.objects.create(session_key="sk-comanda", kds_instance=station, items=[])
    assert kds.start_ticket(ticket, actor="caixa")
    ticket.refresh_from_db()
    assert ticket.started_by == "caixa"
    assert ticket.started_at is not None


@pytest.mark.django_db
def test_courier_status_letters_keep_the_hour_each_arrived(settings):
    from shopman.shop.services import courier

    settings.SHOPMAN_COURIER_ADAPTER = "shopman.shop.adapters.courier_mock"
    order = _order("COL-RIDE", status=Order.Status.READY)
    order.data = {**order.data, "courier": {"id_mch": "M1", "status": "D", "status_at": {"D": "2026-10-13T12:00:00+00:00"}}}
    order.save(update_fields=["data"])

    courier.apply_status(order, "A", source="poll", details={})
    courier.apply_status(order, "A", source="webhook", details={})
    order.refresh_from_db()
    status_at = order.data["courier"]["status_at"]
    assert set(status_at) == {"D", "A"}
    accepted = status_at["A"]

    courier.apply_status(order, "N", source="poll", details={})
    order.refresh_from_db()
    block = order.data["courier"]
    # A corrida que falhou vai para o histórico com as horas.
    assert "status_at" not in block
    assert block["attempts"][-1]["status_at"]["A"] == accepted
    assert "N" in block["attempts"][-1]["status_at"]


def _at(hour, minute=0, days_ago=1):
    day = timezone.localdate() - timedelta(days=days_ago)
    return timezone.make_aware(datetime(day.year, day.month, day.day, hour, minute))


@pytest.mark.django_db
def test_bi_reads_real_prep_by_sku_hour_weekday_and_courier_arrival(station):
    # Pedido 1: KDS iniciou 19:00, Pronto 19:20 (20 min), dois SKUs.
    one = _order("COL-A", status=Order.Status.READY, preparing_at=_at(18, 58), ready_at=_at(19, 20))
    KDSTicket.objects.create(session_key=one.session_key, kds_instance=station, items=[], status="done",
                             started_at=_at(19, 0), started_by="rafael")
    OrderItem.objects.create(order=one, line_id="1", sku="PAO", name="Pão", qty=2, unit_price_q=500, line_total_q=1000)
    OrderItem.objects.create(order=one, line_id="2", sku="CAFE", name="Café", qty=1, unit_price_q=500, line_total_q=500)
    # Pedido 2: sem início no KDS, usa preparing_at 19:10 → Pronto 19:40 (30 min).
    two = _order("COL-B", status=Order.Status.READY, preparing_at=_at(19, 10), ready_at=_at(19, 40))
    OrderItem.objects.create(order=two, line_id="1", sku="PAO", name="Pão", qty=1, unit_price_q=500, line_total_q=500)
    # Corrida: aberta 19:15, aceita 19:18 (3), coletou 19:30 (15); uma arquivada aceita em 5.
    two.data = {**two.data, "courier": {
        "id_mch": "M2", "status": "E", "requested_at": _at(19, 15).isoformat(),
        "status_at": {"D": _at(19, 15).isoformat(), "A": _at(19, 18).isoformat(), "E": _at(19, 30).isoformat()},
        "attempts": [{"id_mch": "M1", "status": "N", "requested_at": _at(19, 5).isoformat(),
                      "status_at": {"A": _at(19, 10).isoformat()}}],
    }}
    two.save(update_fields=["data"])

    report = build_bi_delivery_timing()
    assert report.prep_samples == 2
    assert report.prep_start_fallbacks == 1
    by_sku = {row.key: row for row in report.prep_by_sku}
    assert (by_sku["PAO"].samples, by_sku["PAO"].median_minutes) == (2, 25.0)
    assert (by_sku["CAFE"].samples, by_sku["CAFE"].median_minutes, by_sku["CAFE"].label) == (1, 20.0, "Café")
    assert [(row.label, row.median_minutes) for row in report.prep_by_hour] == [("19h", 25.0)]
    weekday = _at(19).weekday()
    assert [row.key for row in report.prep_by_weekday] == [str(weekday)]

    assert report.rides == 2
    assert [(row.label, row.samples, row.median_minutes) for row in report.courier_accept_by_hour] == [("19h", 2, 4.0)]
    assert [(row.samples, row.median_minutes) for row in report.courier_pickup_by_weekday] == [(1, 15.0)]


@pytest.mark.django_db
def test_bi_endpoint_is_for_who_reads_the_bi(client, station):
    user = User.objects.create_user("bi-entrega", password="pw", is_staff=True)
    client.force_login(user)
    url = reverse("api-backstage-bi-delivery-timing")
    assert client.get(url).status_code == 403
    user.user_permissions.add(
        Permission.objects.get(content_type=ContentType.objects.get_for_model(DayClosing), codename="view_bi"),
    )
    body = client.get(url).json()["bi"]
    assert body["prep_samples"] == 0
    assert body["prep_by_sku"] == []
