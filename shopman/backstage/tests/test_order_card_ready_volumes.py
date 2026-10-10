"""V4-G4: os dois dados do cartão do Gestor que faltavam.

- **Hora do pronto** (``ready_at_iso``): a última entrada em READY, para o
  "pronto há N min". ``Order.ready_at`` guarda só a primeira; depois do pronto
  desfeito (ou do recall da Cozinha) o pedido volta a pronto e o relógio recomeça.
- **Volumes** (``volumes``): declarados por quem embalou, em ``Order.data["volumes"]``.
  Sem declaração o cartão segue contando itens: nenhum volume deduzido.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.contrib.auth.models import Permission, User
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse
from django.utils import timezone
from shopman.orderman.models import Order, OrderEvent, OrderItem

from shopman.backstage.projections.order_queue import build_order_card, build_two_zone_queue
from shopman.backstage.tests._order_intent import context_payload
from shopman.shop.models import Channel, Shop

pytestmark = pytest.mark.django_db


@pytest.fixture
def operator(db):
    Shop.objects.create(name="Loja")
    Channel.objects.create(ref="web", name="Loja online", config={})
    user = User.objects.create_user("gestor-volumes", password="pw", is_staff=True)
    user.user_permissions.add(Permission.objects.get(
        content_type=ContentType.objects.get(app_label="shop", model="shop"), codename="manage_orders",
    ))
    return user


def _order(ref: str, status=Order.Status.PREPARING, **data) -> Order:
    order = Order.objects.create(
        ref=ref, channel_ref="web", session_key=f"sk-{ref}", status=status, total_q=1500,
        data={"customer": {"name": "Ana"}, "fulfillment_type": "pickup", "payment": {"method": "cash"}, **data},
    )
    OrderItem.objects.create(order=order, line_id="1", sku="PAO", name="Pão", qty=1, unit_price_q=1500, line_total_q=1500)
    return order


def _queue_card(ref: str):
    queue = build_two_zone_queue()
    cards = [*queue.intake, *queue.prep, *queue.expedition_pickup, *queue.expedition_delivery, *queue.expedition_delivery_transit]
    return next(card for card in cards if card.ref == ref)


def test_ready_moment_is_the_last_entry_into_ready_not_the_first():
    order = _order("RDY-1", status=Order.Status.ACCEPTED)
    order.transition_status(Order.Status.PREPARING)
    order.transition_status(Order.Status.READY)
    first = order.ready_at
    # O pronto foi desfeito (volta ao preparo) e a Cozinha concluiu de novo depois.
    order.transition_status(Order.Status.PREPARING)
    order.transition_status(Order.Status.READY)
    later = timezone.now() + timedelta(minutes=7)
    last_event = OrderEvent.objects.filter(order=order, type="status_changed").order_by("-seq").first()
    OrderEvent.objects.filter(pk=last_event.pk).update(created_at=later)

    order.refresh_from_db()
    assert order.ready_at == first  # o Core guarda a primeira vez
    assert _queue_card(order.ref).ready_at_iso == later.isoformat()
    assert build_order_card(order).ready_at_iso == later.isoformat()


def test_ready_moment_is_empty_outside_ready_and_dispatch_moment_on_the_road():
    preparing = _order("RDY-2")
    assert _queue_card(preparing.ref).ready_at_iso == ""

    on_road = _order("RDY-3", status=Order.Status.READY, fulfillment_type="delivery")
    on_road.transition_status(Order.Status.DISPATCHED)
    card = _queue_card(on_road.ref)
    assert card.ready_at_iso == ""
    on_road.refresh_from_db()
    assert card.dispatched_at_iso == on_road.dispatched_at.isoformat()


def test_ready_moment_falls_back_to_the_core_stamp_without_an_event():
    order = _order("RDY-4", status=Order.Status.READY)
    stamped = timezone.now() - timedelta(minutes=3)
    Order.objects.filter(pk=order.pk).update(ready_at=stamped)
    OrderEvent.objects.filter(order=order).delete()
    order.refresh_from_db()
    assert _queue_card(order.ref).ready_at_iso == stamped.isoformat()


def test_volumes_are_zero_until_someone_declares_them():
    order = _order("VOL-1", status=Order.Status.READY)
    assert _queue_card(order.ref).volumes == 0
    assert _queue_card(order.ref).items_count == 1


def test_declare_volumes_through_the_intention_protocol(client, operator):
    client.force_login(operator)
    order = _order("VOL-2", status=Order.Status.READY)

    response = client.post(
        reverse("api-backstage-order-volumes", args=[order.ref]),
        context_payload(client, order.ref, "volumes", volumes=3),
        content_type="application/json",
    )
    assert response.status_code == 200, response.json()
    order.refresh_from_db()
    assert order.data["volumes"] == 3
    assert _queue_card(order.ref).volumes == 3
    event = OrderEvent.objects.get(order=order, type="volumes_declared", payload__volumes=3)
    # Quem e de onde: o ⋯ do cartão do Gestor é a superfície padrão.
    assert event.payload == {"volumes": 3, "actor": operator.username, "surface": "orders"}
    assert event.actor == operator.username

    # Zero apaga a declaração: o cartão volta a contar itens.
    response = client.post(
        reverse("api-backstage-order-volumes", args=[order.ref]),
        context_payload(client, order.ref, "volumes", volumes=0),
        content_type="application/json",
    )
    assert response.status_code == 200, response.json()
    order.refresh_from_db()
    assert "volumes" not in order.data


@pytest.mark.parametrize("bad", [-1, 100, "2", True, 1.5])
def test_declare_volumes_refuses_what_is_not_a_count(client, operator, bad):
    client.force_login(operator)
    order = _order(f"VOL-BAD-{abs(hash(str(bad))) % 1000}", status=Order.Status.READY)
    response = client.post(
        reverse("api-backstage-order-volumes", args=[order.ref]),
        context_payload(client, order.ref, "volumes", volumes=bad),
        content_type="application/json",
    )
    assert response.status_code == 400
    order.refresh_from_db()
    assert "volumes" not in order.data


def test_declare_volumes_with_a_stale_revision_is_409(client, operator):
    client.force_login(operator)
    order = _order("VOL-3", status=Order.Status.READY)
    payload = context_payload(client, order.ref, "volumes", volumes=2)
    Order.objects.filter(pk=order.pk).update(data={**order.data, "volumes": 4})

    response = client.post(reverse("api-backstage-order-volumes", args=[order.ref]), payload, content_type="application/json")
    assert response.status_code == 409
    order.refresh_from_db()
    assert order.data["volumes"] == 4


def test_declare_volumes_needs_board_access(client, operator):
    viewer = User.objects.create_user("so-ve", password="pw", is_staff=True)
    client.force_login(viewer)
    order = _order("VOL-4", status=Order.Status.READY)
    response = client.post(
        reverse("api-backstage-order-volumes", args=[order.ref]),
        {"volumes": 2, "base_revision": "x", "expected_actor_id": viewer.pk, "idempotency_key": "k"},
        content_type="application/json",
    )
    assert response.status_code == 403


def _expediter():
    """Quem só expede (``backstage.operate_kds``): a Cozinha e o posto Saída."""
    user = User.objects.create_user("cozinha-volumes", password="pw", is_staff=True)
    user.user_permissions.add(Permission.objects.get(
        content_type__app_label="backstage", codename="operate_kds",
    ))
    return user


def _volumes_payload(order: Order, user, **inputs) -> dict:
    from uuid import uuid4

    from shopman.shop.services.operator_orders import operational_revision

    return {
        **inputs,
        "expected_actor_id": user.pk,
        "base_revision": operational_revision(order, field="volumes"),
        "idempotency_key": str(uuid4()),
    }


def test_whoever_packed_declares_from_the_kitchen_with_who_and_where(client, operator):
    """Quem só expede (Cozinha, posto Saída) também declara; o evento diz quem e de onde."""
    cook = _expediter()
    client.force_login(cook)
    order = _order("VOL-KDS", status=Order.Status.PREPARING)

    card = build_order_card(order, user=cook)
    action = next(action for action in card.actions if action.ref == "volumes")
    assert action.enabled

    response = client.post(
        reverse("api-backstage-order-volumes", args=[order.ref]),
        _volumes_payload(order, cook, volumes=2, surface="kds"),
        content_type="application/json",
    )
    assert response.status_code == 200, response.json()
    order.refresh_from_db()
    assert order.data["volumes"] == 2
    event = OrderEvent.objects.get(order=order, type="volumes_declared")
    assert event.payload == {"volumes": 2, "actor": "cozinha-volumes", "surface": "kds"}


def test_declare_volumes_from_the_exit_post(client, operator):
    client.force_login(operator)
    order = _order("VOL-EXIT", status=Order.Status.READY)
    response = client.post(
        reverse("api-backstage-order-volumes", args=[order.ref]),
        context_payload(client, order.ref, "volumes", volumes=4, surface="exit"),
        content_type="application/json",
    )
    assert response.status_code == 200, response.json()
    assert OrderEvent.objects.get(order=order, type="volumes_declared").payload["surface"] == "exit"


def test_declare_volumes_refuses_an_unknown_surface(client, operator):
    client.force_login(operator)
    order = _order("VOL-SURF", status=Order.Status.READY)
    response = client.post(
        reverse("api-backstage-order-volumes", args=[order.ref]),
        context_payload(client, order.ref, "volumes", volumes=2, surface="pdv"),
        content_type="application/json",
    )
    assert response.status_code == 400
    assert response.json()["field"] == "surface"
    order.refresh_from_db()
    assert "volumes" not in order.data
