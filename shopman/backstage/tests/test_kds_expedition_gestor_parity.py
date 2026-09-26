"""A Saída do KDS é outra porta de saída — e a saída tem uma implementação só.

Três contratos, todos achados na auditoria de 21/09/2026:

1. "Despachar" pela Saída passa pelo MESMO ``operator_orders.advance_order``
   do Gestor: fulfillment de entrega avança, a auto-conclusão fica agendada e,
   quando o pedido pede troco (que só o Gestor sabe perguntar), a Saída
   recusa com "abra no Gestor" — e o card diz isso antes do toque. Antes ela
   fazia a transição sozinha: entrega sem auto-conclusão e troco saindo da
   gaveta sem a linha ``courier_out`` que o acerto exige.
2. "Desfazer finalização" não reabre ticket de pedido que já saiu da cozinha
   (despachado, concluído, cancelado), e a lista de concluídos não o oferece.
3. O painel público de retirada é do DIA: pedido esquecido de dias atrás e
   encomenda de amanhã não aparecem.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta

import pytest
from django.utils import timezone
from shopman.orderman.models import Directive, Order, OrderItem, Session

from shopman.backstage.models import KDSInstance, KDSTicket
from shopman.backstage.projections.kds import build_kds_board, build_kds_customer_status
from shopman.backstage.services import kds as kds_backstage
from shopman.backstage.services.exceptions import KDSError
from shopman.shop.directives import DELIVERY_AUTO_COMPLETE
from shopman.shop.models import Channel, Shop
from shopman.shop.services import kds as kds_core

pytestmark = pytest.mark.django_db

GESTOR_CHANGE = "Abra este pedido no Gestor e informe o troco que o entregador leva."


@pytest.fixture
def expedition(db):
    Shop.objects.create(name="Loja")
    Channel.objects.create(ref="web", name="Loja online", config={})
    return KDSInstance.objects.create(ref="exp-parity", name="Saída", type="expedition")


def _cod_order(ref: str, *, change_for_q: int | None = None) -> Order:
    payment = {"method": "cash", "collection": "on_delivery"}
    if change_for_q is not None:
        payment["change_for_q"] = change_for_q
    order = Order.objects.create(
        ref=ref,
        channel_ref="web",
        session_key=f"sk-{ref}",
        status=Order.Status.READY,
        total_q=3000,
        data={"customer": {"name": "Ana"}, "fulfillment_type": "delivery", "payment": payment},
    )
    OrderItem.objects.create(order=order, line_id="1", sku="PAO", name="Pão", qty=1, unit_price_q=3000, line_total_q=3000)
    return order


def _card(board, ref):
    return next(card for card in board.tickets if card.order_ref == ref)


# ── 1. Despachar pela Saída = despachar pelo Gestor ─────────────────────


def test_dispatch_with_change_is_refused_and_the_card_says_so_before_the_tap(expedition):
    order = _cod_order("EXP-TROCO", change_for_q=5000)

    card = _card(build_kds_board(expedition.ref), "EXP-TROCO")
    assert card.advance_block_label == "Despachar pelo Gestor"
    assert card.advance_block_reason == GESTOR_CHANGE

    with pytest.raises(KDSError, match="troco"):
        kds_backstage.expedition_action(order_id=order.pk, action="dispatch", actor="kds:op")
    order.refresh_from_db()
    assert order.status == Order.Status.READY


def test_dispatch_without_change_goes_through_the_gestor_service(expedition):
    order = _cod_order("EXP-SEMTROCO")

    card = _card(build_kds_board(expedition.ref), "EXP-SEMTROCO")
    assert card.advance_block_label == ""

    status = kds_backstage.expedition_action(order_id=order.pk, action="dispatch", actor="kds:op")

    assert status == Order.Status.DISPATCHED
    order.refresh_from_db()
    assert order.status == Order.Status.DISPATCHED
    # O que o Gestor faz no despacho e a Saída pulava:
    assert order.fulfillments.get().status == "dispatched"
    assert Directive.objects.filter(
        topic=DELIVERY_AUTO_COMPLETE, payload__order_ref="EXP-SEMTROCO", status=Directive.Status.QUEUED
    ).exists()


# ── 2. Desfazer finalização só enquanto a cozinha responde pelo pedido ──────


@pytest.fixture
def prep():
    Shop.objects.create(name="Loja")
    return KDSInstance.objects.create(ref="prep-parity", name="Preparo", type="prep", target_time_minutes=10)


def _done_ticket(prep, ref: str, status: str) -> KDSTicket:
    order = Order.objects.create(
        ref=ref, channel_ref="web", session_key=f"sk-{ref}", status=status, total_q=1000,
        data={"fulfillment_type": "pickup"},
    )
    return KDSTicket.objects.create(
        session_key=order.session_key,
        kds_instance=prep,
        items=[{"sku": "SKU", "name": "Produto", "qty": 1}],
        status="done",
        completed_at=timezone.now(),
    )


@pytest.mark.parametrize("status", [Order.Status.DISPATCHED, Order.Status.COMPLETED, Order.Status.CANCELLED])
def test_recall_is_refused_once_the_order_left_the_kitchen(prep, status):
    ticket = _done_ticket(prep, f"RCL-{status}", status)

    assert ticket.pk not in {t.pk for t in build_kds_board(prep.ref).recent_done}
    with pytest.raises(KDSError, match="não pode mais ser desfeita"):
        kds_backstage.recall_ticket(ticket_pk=ticket.pk, actor="kds:op")
    ticket.refresh_from_db()
    assert ticket.status == "done"
    assert Order.objects.get(ref=f"RCL-{status}").status == status


def test_recall_still_pulls_a_ready_order_back_to_preparing(prep):
    ticket = _done_ticket(prep, "RCL-READY", Order.Status.READY)

    assert ticket.pk in {t.pk for t in build_kds_board(prep.ref).recent_done}
    kds_backstage.recall_ticket(ticket_pk=ticket.pk, actor="kds:op")

    ticket.refresh_from_db()
    assert ticket.status == "in_progress"
    assert Order.objects.get(ref="RCL-READY").status == Order.Status.PREPARING


def test_recall_block_reason_speaks_the_order_status():
    order = Order(ref="X", status=Order.Status.DISPATCHED)
    assert kds_core.recall_block_reason(order) == (
        "O pedido já está despachado: a finalização não pode mais ser desfeita."
    )
    assert kds_core.recall_block_reason(Order(ref="Y", status=Order.Status.READY)) == ""


# ── 3. O painel de retirada é do dia ────────────────────────────────────────


def _pickup(ref: str, status: str, *, created_days_ago: int = 0, delivery_date=None) -> Order:
    data = {"fulfillment_type": "pickup"}
    if delivery_date is not None:
        data["delivery_date"] = delivery_date.isoformat()
    order = Order.objects.create(ref=ref, channel_ref="pos", status=status, total_q=1000, data=data)
    if created_days_ago:
        past = timezone.now() - timedelta(days=created_days_ago)
        Order.objects.filter(pk=order.pk).update(created_at=past, updated_at=past, ready_at=past)
    return order


def test_pickup_board_shows_only_the_day(db):
    Shop.objects.create(name="Loja")
    today = timezone.localdate()
    _pickup("PDV-OLD-READY", Order.Status.READY, created_days_ago=7)
    _pickup("PDV-OLD-PREP", Order.Status.PREPARING, created_days_ago=16)
    _pickup("WEB-TOMORROW", Order.Status.ACCEPTED, delivery_date=today + timedelta(days=1))
    _pickup("PDV-TODAY-READY", Order.Status.READY)
    _pickup("PDV-TODAY-PREP", Order.Status.PREPARING)
    # Encomenda feita dias atrás PARA hoje: é do dia.
    _pickup("WEB-PREORDER-TODAY", Order.Status.ACCEPTED, created_days_ago=3, delivery_date=today)
    # Comanda aberta esquecida desde ontem com linhas na cozinha.
    stale = Session.objects.create(
        session_key="sk-stale-tab", state="open", handle_ref="2001",
        data={"fired_lines": ["1"], "tab_ref": "00002001", "fulfillment_type": "pickup"},
    )
    yesterday = timezone.make_aware(datetime.combine(today - timedelta(days=1), time(12)))
    Session.objects.filter(pk=stale.pk).update(updated_at=yesterday)

    status = build_kds_customer_status()

    assert [p.ref for p in status.ready] == ["PDV-TODAY-READY"]
    preparing = {p.ref for p in status.preparing}
    assert preparing == {"PDV-TODAY-PREP", "WEB-PREORDER-TODAY"}
