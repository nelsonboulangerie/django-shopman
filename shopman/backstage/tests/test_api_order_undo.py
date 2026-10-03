"""UX-G2 na superfície: Gestor e Saída da Cozinha com desfazer no servidor.

O Gestor lê o bloco ``undo`` e as ações ``undo-handoff``/``undo-ready`` da
projeção e manda a intenção pelo mesmo protocolo das outras ações (chave de
idempotência, revisão, pessoa). A Saída usa o endpoint próprio com o token do
card. O servidor só aceita dentro da janela.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.contrib.auth.models import Permission, User
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse
from django.utils import timezone
from shopman.orderman.models import Order, OrderItem

from shopman.backstage.models import KDSInstance, KDSTicket
from shopman.backstage.projections.kds import build_kds_board
from shopman.backstage.tests._order_intent import advance_payload, context_payload
from shopman.shop.models import Channel, Shop
from shopman.shop.services import kds as kds_core
from shopman.shop.tests._handoff import settle

pytestmark = pytest.mark.django_db


@pytest.fixture
def operator(db):
    Shop.objects.create(name="Loja")
    Channel.objects.create(ref="web", name="Loja online", config={})
    user = User.objects.create_user("gestor-undo", password="pw", is_staff=True)
    user.user_permissions.add(Permission.objects.get(
        content_type=ContentType.objects.get(app_label="shop", model="shop"), codename="manage_orders",
    ))
    user.user_permissions.add(Permission.objects.get(
        content_type=ContentType.objects.get(app_label="backstage", model="kdsticket"), codename="operate_kds",
    ))
    return user


def _order(ref: str, status=Order.Status.READY, fulfillment="pickup") -> Order:
    order = Order.objects.create(
        ref=ref, channel_ref="web", session_key=f"sk-{ref}", status=status, total_q=1500,
        data={"customer": {"name": "Ana"}, "fulfillment_type": fulfillment, "payment": {"method": "cash"}},
    )
    OrderItem.objects.create(order=order, line_id="1", sku="PAO", name="Pão", qty=1, unit_price_q=1500, line_total_q=1500)
    return order


def _detail(client, ref):
    return client.get(reverse("api-backstage-order-detail", args=[ref])).json()["order"]


def _expire(order, key, field):
    order.refresh_from_db()
    data = dict(order.data)
    data[key] = {**data[key], field: (timezone.now() - timedelta(seconds=1)).isoformat()}
    Order.objects.filter(pk=order.pk).update(data=data)


def test_gestor_handoff_then_undo_inside_the_window(client, operator):
    client.force_login(operator)
    order = _order("UNDO-API-1")

    response = client.post(reverse("api-backstage-order-advance", args=[order.ref]), advance_payload(client, order.ref), content_type="application/json")
    assert response.status_code == 200, response.json()
    projected = response.json()["order"]
    assert projected["status"] == "ready"
    assert projected["undo"]["kind"] == "handoff"
    assert projected["undo"]["label"].startswith("Entregue às ")
    assert projected["undo"]["undo_until_iso"]
    assert [a["ref"] for a in projected["actions"] if a["ref"] in ("advance", "undo-handoff")] == ["undo-handoff"]

    undo = client.post(reverse("api-backstage-order-undo-handoff", args=[order.ref]), context_payload(client, order.ref, "undo-handoff"), content_type="application/json")
    assert undo.status_code == 200, undo.json()
    after = undo.json()["order"]
    assert after["status"] == "ready"
    assert after["undo"] is None
    assert any(a["ref"] == "advance" for a in after["actions"])
    order.refresh_from_db()
    assert "pending_handoff" not in order.data


def test_gestor_undo_after_the_window_is_409_and_the_handoff_stands(client, operator):
    client.force_login(operator)
    order = _order("UNDO-API-2")
    client.post(reverse("api-backstage-order-advance", args=[order.ref]), advance_payload(client, order.ref), content_type="application/json")
    payload = context_payload(client, order.ref, "undo-handoff")
    _expire(order, "pending_handoff", "commit_at")

    undo = client.post(reverse("api-backstage-order-undo-handoff", args=[order.ref]), payload, content_type="application/json")
    assert undo.status_code == 409
    assert settle(order) == Order.Status.COMPLETED


def test_gestor_undo_ready_reopens_the_ticket(client, operator):
    client.force_login(operator)
    order = _order("UNDO-API-3", status=Order.Status.PREPARING)
    station = KDSInstance.objects.create(ref="forno", name="Forno", type="prep")
    ticket = KDSTicket.objects.create(session_key=order.session_key, kds_instance=station, status="in_progress", items=[{"sku": "PAO", "name": "Pão", "qty": 1}])
    kds_core.complete_ticket(ticket, actor="kds:op")

    projected = _detail(client, order.ref)
    assert projected["status"] == "ready"
    assert projected["undo"]["kind"] == "auto_ready"
    assert projected["undo"]["label"] == "Pronto · automático"
    assert projected["undo"]["held_effect"] == "Aviso de pronto ao cliente"

    response = client.post(reverse("api-backstage-order-undo-ready", args=[order.ref]), context_payload(client, order.ref, "undo-ready"), content_type="application/json")
    assert response.status_code == 200, response.json()
    assert response.json()["order"]["status"] == "preparing"
    ticket.refresh_from_db()
    assert ticket.status == "in_progress"


def test_board_card_carries_the_same_undo_block(client, operator):
    client.force_login(operator)
    order = _order("UNDO-API-4")
    client.post(reverse("api-backstage-order-advance", args=[order.ref]), advance_payload(client, order.ref), content_type="application/json")

    queue = client.get(reverse("api-backstage-orders")).json()["queue"]
    cards = [card for value in queue.values() if isinstance(value, list) for card in value if isinstance(card, dict) and "ref" in card]
    card = next(c for c in cards if c["ref"] == order.ref)
    assert card["undo"]["kind"] == "handoff"
    assert card["can_advance"] is False


def test_saida_handoff_and_undo(client, operator):
    client.force_login(operator)
    expedition = KDSInstance.objects.create(ref="saida-undo", name="Saída", type="expedition")
    order = _order("UNDO-API-5")

    response = client.post(reverse("api-backstage-kds-expedition", args=[order.pk]), {"action": "complete"}, content_type="application/json")
    assert response.status_code == 200
    body = response.json()
    assert body["handoff_label"].startswith("Entregue às ")
    assert body["handoff_token"]

    card = next(c for c in build_kds_board(expedition.ref).tickets if getattr(c, "order_ref", "") == order.ref)
    assert card.handoff_token == body["handoff_token"]
    assert card.handoff_undo_until_iso

    stale = client.post(reverse("api-backstage-kds-expedition-undo", args=[order.pk]), {"token": "outro"}, content_type="application/json")
    assert stale.status_code == 409
    undo = client.post(reverse("api-backstage-kds-expedition-undo", args=[order.pk]), {"token": body["handoff_token"]}, content_type="application/json")
    assert undo.status_code == 200
    order.refresh_from_db()
    assert order.status == Order.Status.READY
    assert "pending_handoff" not in order.data


def _cash_delivery(ref: str) -> Order:
    order = Order.objects.create(
        ref=ref, channel_ref="web", session_key=f"sk-{ref}", status=Order.Status.READY, total_q=3000,
        data={"customer": {"name": "Ana"}, "fulfillment_type": "delivery",
              "payment": {"method": "cash", "collection": "on_delivery", "amount_q": 3000, "change_for_q": 5000}},
    )
    OrderItem.objects.create(order=order, line_id="1", sku="PAO", name="Pão", qty=1, unit_price_q=3000, line_total_q=3000)
    return order


def test_dispatch_with_change_leaves_the_drawer_only_when_the_window_ends(client, operator):
    """Troco da gaveta: a linha do livro nasce na gravação, no turno de quem tocou."""
    from shopman.cashman import Entry
    from shopman.cashman import services as cash

    client.force_login(operator)
    shift = cash.open_shift(operator=operator, float_q=10000)
    order = _cash_delivery("UNDO-API-6")

    response = client.post(
        reverse("api-backstage-order-advance", args=[order.ref]),
        advance_payload(client, order.ref, change_out="20,00"), content_type="application/json",
    )
    assert response.status_code == 200, response.json()
    assert response.json()["order"]["undo"]["label"].startswith("Saiu às ")
    order.refresh_from_db()
    assert order.status == Order.Status.READY
    assert not Entry.objects.filter(kind=Entry.Kind.COURIER_OUT, order_ref=order.ref).exists()

    assert settle(order) == Order.Status.DISPATCHED
    line = Entry.objects.get(kind=Entry.Kind.COURIER_OUT, order_ref=order.ref)
    assert (line.amount_q, line.shift_id) == (-2000, shift.pk)


def test_dispatch_undone_never_touches_the_drawer(client, operator):
    from shopman.cashman import Entry
    from shopman.cashman import services as cash

    client.force_login(operator)
    cash.open_shift(operator=operator, float_q=10000)
    order = _cash_delivery("UNDO-API-7")
    client.post(reverse("api-backstage-order-advance", args=[order.ref]), advance_payload(client, order.ref, change_out="20,00"), content_type="application/json")

    undo = client.post(reverse("api-backstage-order-undo-handoff", args=[order.ref]), context_payload(client, order.ref, "undo-handoff"), content_type="application/json")
    assert undo.status_code == 200
    assert settle(order) == ""
    order.refresh_from_db()
    assert order.status == Order.Status.READY
    assert not Entry.objects.filter(order_ref=order.ref).exists()
