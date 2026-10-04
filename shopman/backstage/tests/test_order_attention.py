"""V4-G4: a Fila "Precisa de você" do Gestor no servidor.

O cartão diz o fato humano que o pedido espera (e a meta da etapa); a projeção do
quadro traz, na mesma leitura, o que o sistema fez nos últimos 15 minutos e o estado
do cardápio e dos canais.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.contrib.auth.models import Permission, User
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse
from django.utils import timezone
from shopman.offerman.models import Product
from shopman.orderman.models import Order, OrderEvent, OrderItem

from shopman.backstage.models import KDSInstance, KDSTicket, OutageReason, ShelfOutage
from shopman.backstage.projections.order_queue import build_two_zone_queue
from shopman.shop.models import Channel, Shop
from shopman.shop.services import kds as kds_core

pytestmark = pytest.mark.django_db


@pytest.fixture
def shop(db):
    Shop.objects.create(name="Loja")
    Channel.objects.create(ref="web", name="Loja online", config={})
    return None


@pytest.fixture
def operator(shop):
    user = User.objects.create_user("gestor-fila", password="pw", is_staff=True)
    user.user_permissions.add(Permission.objects.get(
        content_type=ContentType.objects.get(app_label="shop", model="shop"), codename="manage_orders",
    ))
    return user


def _order(ref: str, status=Order.Status.NEW, fulfillment="pickup", payment=None) -> Order:
    order = Order.objects.create(
        ref=ref, channel_ref="web", session_key=f"sk-{ref}", status=status, total_q=1500,
        data={"customer": {"name": "Ana"}, "fulfillment_type": fulfillment, "payment": payment or {"method": "cash"}},
    )
    OrderItem.objects.create(order=order, line_id="1", sku="PAO", name="Pão", qty=1, unit_price_q=1500, line_total_q=1500)
    return order


def _cards(user=None):
    queue = build_two_zone_queue(user=user)
    cards = [*queue.intake, *queue.prep, *queue.expedition_pickup, *queue.expedition_delivery, *queue.expedition_delivery_transit]
    return queue, {card.ref: card for card in cards}


def test_new_order_needs_a_decision_with_the_confirmation_goal(operator):
    _order("ATT-NEW")
    _, cards = _cards(operator)
    card = cards["ATT-NEW"]
    assert card.attention == "confirm"
    assert card.goal_minutes == 5
    assert card.goal_label == "meta 5"
    assert card.attention_since_iso


def test_ready_pickup_waits_the_handoff_counted_from_the_ready(operator):
    order = _order("ATT-RDY", status=Order.Status.PREPARING)
    order.transition_status(Order.Status.READY)
    _, cards = _cards(operator)
    card = cards[order.ref]
    assert card.attention == "handoff"
    assert card.goal_label == "no balcão"
    assert card.ready_at_iso
    assert card.attention_since_iso == card.ready_at_iso


def test_ready_delivery_waits_the_dispatch_against_the_whole_promise(operator):
    order = _order("ATT-DLV", status=Order.Status.READY, fulfillment="delivery")
    _, cards = _cards(operator)
    card = cards[order.ref]
    assert card.attention == "dispatch"
    assert card.goal_label == "meta 30"
    assert card.attention_since_iso == order.created_at.isoformat()


def test_stage_goals_default_to_the_owner_numbers():
    """Sem config de canal valem os padrões do dono (04/10/2026)."""
    from shopman.backstage.projections.order_attention import stage_goal

    assert {kind: stage_goal(kind) for kind in (
        "start", "station", "mark_ready", "handoff", "dispatch", "courier_back", "settle", "blocked",
    )} == {
        "start": 5, "station": 15, "mark_ready": 15, "handoff": 10,
        "dispatch": 30, "courier_back": 45, "settle": 15, "blocked": 5,
    }


def test_station_goal_on_the_card_is_fifteen_by_default(operator):
    preparing = _order("ATT-GOAL-ST", status=Order.Status.PREPARING)
    _, cards = _cards(operator)
    card = cards[preparing.ref]
    assert card.attention == "mark_ready"
    assert card.goal_minutes == 15
    assert card.goal_label == "meta 15"


def test_channel_overrides_one_stage_goal_and_inherits_the_rest(operator):
    """O canal declara só a etapa que muda (cascata por chave); a loja também pode."""
    Channel.objects.filter(ref="web").update(config={"fulfillment": {"stage_goal_minutes": {"dispatch": 40}}})
    shop = Shop.objects.get()
    shop.defaults = {"fulfillment": {"stage_goal_minutes": {"station": 25}}}
    shop.save()
    delivery = _order("ATT-GOAL-DLV", status=Order.Status.READY, fulfillment="delivery")
    preparing = _order("ATT-GOAL-PRP", status=Order.Status.PREPARING)
    ready = _order("ATT-GOAL-RDY", status=Order.Status.READY)
    _, cards = _cards(operator)
    assert cards[delivery.ref].goal_minutes == 40
    assert cards[delivery.ref].goal_label == "meta 40"
    assert cards[preparing.ref].goal_minutes == 25
    assert cards[ready.ref].goal_minutes == 10


def test_stage_goal_config_refuses_unknown_stage_and_non_positive_minutes():
    from shopman.shop.config import ChannelConfig, deep_merge

    for bad in ({"despacho": 30}, {"dispatch": 0}, {"dispatch": "30"}, {"dispatch": True}):
        config = ChannelConfig.from_dict(deep_merge(ChannelConfig.defaults(), {"fulfillment": {"stage_goal_minutes": bad}}))
        with pytest.raises(ValueError, match="stage_goal_minutes"):
            config.validate()


def test_kitchen_work_and_the_road_need_nobody(operator):
    preparing = _order("ATT-PREP", status=Order.Status.PREPARING)
    station = KDSInstance.objects.create(ref="forno-att", name="Forno", type="prep")
    KDSTicket.objects.create(session_key=preparing.session_key, kds_instance=station, status="in_progress", items=[{"sku": "PAO", "name": "Pão", "qty": 1}])
    on_road = _order("ATT-ROAD", status=Order.Status.READY, fulfillment="delivery")
    on_road.transition_status(Order.Status.DISPATCHED)
    _, cards = _cards(operator)
    assert cards[preparing.ref].attention == ""
    assert cards[on_road.ref].attention == ""
    assert cards[on_road.ref].goal_label == ""


def test_system_did_lists_the_automatic_ready_with_undo_inside_the_window(operator):
    order = _order("ATT-AUTO", status=Order.Status.PREPARING)
    station = KDSInstance.objects.create(ref="forno-auto", name="Forno", type="prep")
    ticket = KDSTicket.objects.create(session_key=order.session_key, kds_instance=station, status="in_progress", items=[{"sku": "PAO", "name": "Pão", "qty": 1}])
    kds_core.complete_ticket(ticket, actor="kds:op")

    queue, _ = _cards(operator)
    lines = [line for line in queue.awareness.system_actions if line.order_ref == order.ref]
    assert len(lines) == 1
    assert lines[0].verb == "Pronto"
    assert lines[0].reason == "Cozinha concluiu"
    assert lines[0].undo_action == "undo-ready"
    assert lines[0].undo_until_iso


def test_system_did_ignores_what_a_person_did_and_old_events(operator):
    manual = _order("ATT-MAN", status=Order.Status.READY)
    manual.transition_status(Order.Status.COMPLETED, actor="gestor:ana")
    timed = _order("ATT-TIME")
    timed.transition_status(Order.Status.ACCEPTED, actor="confirmation.timeout")
    old = _order("ATT-OLD")
    old.transition_status(Order.Status.ACCEPTED, actor="confirmation.timeout")
    OrderEvent.objects.filter(order=old).update(created_at=timezone.now() - timedelta(minutes=20))

    queue, _ = _cards(operator)
    refs = {line.order_ref: line for line in queue.awareness.system_actions}
    assert "ATT-MAN" not in refs
    assert "ATT-OLD" not in refs
    assert refs["ATT-TIME"].verb == "Aceito"
    assert refs["ATT-TIME"].reason == "prazo de confirmação"
    assert refs["ATT-TIME"].undo_action == ""


def test_menu_lists_open_outages_one_per_product(operator):
    Product.objects.create(sku="BICHON", name="Bichon au Citron", base_price_q=1200)
    Channel.objects.create(ref="ifood", name="iFood", config={})
    now = timezone.now()
    ShelfOutage.objects.create(sku="BICHON", channel_ref="web", reason=OutageReason.SOLD_OUT, started_at=now - timedelta(minutes=5))
    ShelfOutage.objects.create(sku="BICHON", channel_ref="ifood", reason=OutageReason.SOLD_OUT, started_at=now - timedelta(minutes=4))
    ShelfOutage.objects.create(sku="BICHON", channel_ref="web", reason=OutageReason.SOLD_OUT, started_at=now - timedelta(hours=3), ended_at=now - timedelta(hours=2))

    queue, _ = _cards(operator)
    outages = queue.awareness.menu_outages
    assert [o.sku for o in outages] == ["BICHON"]
    assert outages[0].line == "Bichon au Citron esgotado"
    assert outages[0].detail.startswith("fora de ")
    assert "Loja online" in outages[0].detail and "iFood" in outages[0].detail


def test_board_endpoint_carries_the_awareness_block(client, operator):
    client.force_login(operator)
    _order("ATT-API")
    body = client.get(reverse("api-backstage-orders")).json()["queue"]
    assert set(body["awareness"]) >= {"system_actions", "menu_outages", "menu_channels", "system_window_minutes", "can_open_channels"}
    assert body["awareness"]["system_window_minutes"] == 15
    card = next(c for c in body["intake"] if c["ref"] == "ATT-API")
    assert card["attention"] == "confirm"


def test_product_detail_says_where_it_can_be_bought_now(shop):
    from shopman.backstage.services.catalog import get_product_detail

    Product.objects.create(sku="CROISSANT", name="Croissant Manteiga", base_price_q=1300)
    Channel.objects.create(ref="ifood", name="iFood", config={})
    ShelfOutage.objects.create(sku="CROISSANT", channel_ref="ifood", reason=OutageReason.SOLD_OUT, started_at=timezone.now())

    rows = {row["ref"]: row for row in get_product_detail("CROISSANT")["channel_availability"]}
    assert rows["web"]["state"] == "available"
    assert rows["ifood"]["state"] == "sold_out"
    assert rows["ifood"]["since"]
    assert rows["ifood"]["automatic"] is True
    assert rows["web"]["automatic"] is False
