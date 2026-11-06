"""Beta test do Gestor de pedidos, 05/11/2026 (frente gestor-pedidos).

Travas dos achados que eram do servidor:

- GES-02: o motivo e a observação interna do cancelamento na linha do tempo;
- GES-07: "item = unidade, nunca linha" no cartão;
- GES-09: o bloqueio do iFood com um próximo passo de balcão;
- GES-10/GES-15: pedido encerrado não oferece (nem aceita) nota da cozinha,
  volumes e atendimento;
- GES-05/GES-16: Pix vencido marcado na projeção, para a tela oferecer o cancelar;
- PDV-10: quem fez, na linha do tempo, é nome de gente ou de ato, nunca código.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.auth.models import Permission, User
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone
from shopman.orderman.models import Order, OrderItem

from shopman.backstage.projections.order_queue import build_operator_order, build_order_card
from shopman.shop.services import cancellation, operator_orders

pytestmark = [pytest.mark.django_db, pytest.mark.channels("web")]


def _order(ref: str, status: str = "accepted", *, items=(("PAO", "Pão", 1),), payment: dict | None = None) -> Order:
    order = Order.objects.create(
        ref=ref, channel_ref="web", session_key=f"s-{ref}", status=status, total_q=1500,
        data={
            "customer": {"name": "Ana"}, "fulfillment_type": "pickup",
            "payment": payment or {"method": "cash"},
            "availability_decision": {"approved": True, "decisions": []},
        },
    )
    for index, (sku, name, qty) in enumerate(items):
        OrderItem.objects.create(
            order=order, line_id=f"{ref}-{index}", sku=sku, name=name, qty=Decimal(str(qty)),
            unit_price_q=500, line_total_q=500,
        )
    return order


@pytest.fixture
def gestor(db):
    user = User.objects.create_user("beta-gestor", password="pw", is_staff=True, first_name="Fran")
    user.user_permissions.add(Permission.objects.get(
        content_type=ContentType.objects.get(app_label="shop", model="shop"), codename="manage_orders",
    ))
    return user


# ── GES-07 ──────────────────────────────────────────────────────────────────


def test_card_counts_units_not_lines():
    """3x Croissant são 3 itens; 2 + 3 são 5. Peso (kg) conta 1 por linha."""
    assert build_order_card(_order("B-M99", items=(("CRO", "Croissant", 3),))).items_count == 3
    assert build_order_card(_order("B-K49", items=(("CRO", "Croissant", 2), ("CAF", "Café", 3)))).items_count == 5
    assert build_order_card(_order("B-KG", items=(("QUE", "Queijo", "0.350"), ("PAO", "Pão", 2)))).items_count == 3


# ── GES-02 ──────────────────────────────────────────────────────────────────


def test_cancelled_event_carries_reason_and_internal_note():
    order = _order("B-K38")
    assert cancellation.cancel(
        order, reason="operator", actor="gestor:beta-gestor",
        extra_data={"cancellation_reason_key": "payment_not_confirmed", "cancellation_internal_note": "Cliente não respondeu"},
    )
    timeline = build_operator_order(Order.objects.get(pk=order.pk)).timeline
    cancelled = [event for event in timeline if event.label == "Cancelado"]
    assert cancelled and cancelled[-1].detail == "Pagamento não confirmado: Cliente não respondeu"


def test_cancelled_without_note_shows_only_the_reason():
    order = _order("B-K39")
    assert cancellation.cancel(order, reason="pix_timeout", actor="payment.timeout")
    cancelled = [e for e in build_operator_order(Order.objects.get(pk=order.pk)).timeline if e.label == "Cancelado"]
    assert cancelled[-1].detail == "O Pix venceu"
    assert cancelled[-1].actor == "Prazo do pagamento"


# ── PDV-10 ──────────────────────────────────────────────────────────────────


def test_timeline_actor_is_a_person_or_an_act_never_a_code(gestor):
    order = _order("B-L14")
    order.emit_event(event_type="operator_comment", actor="pos:beta-gestor", payload={"note": "oi"})
    order.emit_event(event_type="operator_comment", actor="auto_confirm", payload={"note": "a"})
    order.emit_event(event_type="operator_comment", actor="system:counter_handoff", payload={"note": "b"})
    order.emit_event(event_type="operator_comment", actor="lifecycle.on_ready", payload={"note": "c"})
    order.emit_event(event_type="operator_comment", actor="pos:sem-cadastro", payload={"note": "d"})
    actors = [e.actor for e in build_operator_order(Order.objects.get(pk=order.pk)).timeline if e.event_type == "operator_comment"]
    assert actors == ["Fran", "Confirmação automática", "Entrega no balcão", "", "sem-cadastro"]


# ── GES-10 / GES-15 ─────────────────────────────────────────────────────────


@pytest.mark.parametrize("status", ["cancelled", "completed"])
def test_closed_order_turns_off_kitchen_note_volumes_and_assign(gestor, status):
    order = _order(f"B-END-{status}", status=status)
    actions = {action.ref: action for action in operator_orders.operational_actions(order, user=gestor)}
    for ref in ("notes", "volumes", "assign"):
        assert actions[ref].enabled is False, ref
        assert actions[ref].reason == "Pedido encerrado."
    assert actions["comment"].enabled is True


def test_open_order_keeps_kitchen_note_editable(gestor):
    actions = {a.ref: a for a in operator_orders.operational_actions(_order("B-OPEN"), user=gestor)}
    assert actions["notes"].enabled and actions["volumes"].enabled and actions["assign"].enabled


def test_server_refuses_kitchen_note_volumes_and_assign_on_closed_order():
    order = _order("B-CAN", status="cancelled")
    with pytest.raises(operator_orders.OrderStateConflict, match="Pedido encerrado"):
        operator_orders.save_kitchen_note(order, notes="Bem assado", actor="gestor:x")
    with pytest.raises(operator_orders.OrderStateConflict, match="Pedido encerrado"):
        operator_orders.save_volumes(order, volumes=2, actor="gestor:x")
    with pytest.raises(operator_orders.OrderStateConflict, match="Pedido encerrado"):
        operator_orders.assign_order(order, operator_id=1, operator_name="Fran", actor="gestor:x")
    order.refresh_from_db()
    assert "kitchen_note" not in order.data
    assert not order.events.filter(type="kitchen_note_changed").exists()


# ── GES-09 ──────────────────────────────────────────────────────────────────


def test_ifood_delivery_unknown_gives_a_counter_step_not_integration_jargon():
    message = operator_orders.advance_block_message(operator_orders.AdvanceBlock.IFOOD_DELIVERY_UNKNOWN)
    assert "integração" not in message
    assert "gerente" in message


# ── GES-05 / GES-16 ─────────────────────────────────────────────────────────


def _pix(ref: str, *, minutes_ago: int) -> Order:
    from shopman.payman.models import PaymentIntent

    order = _order(ref, payment={"method": "pix", "amount_q": 1500, "intent_ref": f"INT-{ref}"})
    created = timezone.now() - timedelta(minutes=minutes_ago)
    intent = PaymentIntent.objects.create(
        ref=f"INT-{ref}", order_ref=order.ref, method="pix", amount_q=1500, status="pending",
        expires_at=created + timedelta(minutes=30),
    )
    PaymentIntent.objects.filter(pk=intent.pk).update(created_at=created)
    return Order.objects.get(pk=order.pk)


def test_lapsed_pix_is_flagged_for_the_ready_cancel(gestor):
    lapsed = _pix("B-Z68", minutes_ago=50)
    assert build_order_card(lapsed).payment_lapsed is True
    assert build_operator_order(lapsed, user=gestor).payment_lapsed is True
    waiting = _pix("B-Z69", minutes_ago=5)
    assert build_order_card(waiting).payment_lapsed is False
    assert build_operator_order(waiting, user=gestor).payment_lapsed is False


# ── GES-11 ──────────────────────────────────────────────────────────────────


def test_skipped_notice_says_why_instead_of_omitted():
    from shopman.backstage.projections import notification_receipts as receipts

    suppressed = receipts._detail(receipts.STATE_SKIPPED, {"reason": "external_suppressed:seed"})
    assert suppressed == "Avisos ao cliente desligados neste ambiente."
    counter = receipts._detail(receipts.STATE_SKIPPED, {"reason": "payment_taken_over_at_counter"})
    assert counter == "O pagamento passou para o balcão."
    unknown = receipts._detail(receipts.STATE_SKIPPED, {"reason": "algo_novo"})
    assert "omitido" not in unknown and "outro meio" in unknown
    assert "outro meio" in receipts._detail(receipts.STATE_FAILED, {})


# ── PDV-10 (cliente) ────────────────────────────────────────────────────────


def test_pos_tab_handle_is_never_shown_as_the_customer(gestor):
    """O handle da comanda ("00001008") não é nome de cliente; o telefone é."""
    order = _order("B-L15")
    order.data = {**order.data, "customer": {}}
    order.handle_type, order.handle_ref = "pos_tab", "00001008"
    order.save(update_fields=["data", "handle_type", "handle_ref"])
    assert build_order_card(order).customer_name == ""
    assert build_operator_order(order, user=gestor).customer_name == ""
    order.handle_type, order.handle_ref = "phone", "+5543999990000"
    order.save(update_fields=["handle_type", "handle_ref"])
    assert build_order_card(order).customer_name != ""


# ── PDV2-03 ─────────────────────────────────────────────────────────────────


def test_preorder_not_due_block_says_what_it_waits_for():
    from shopman.backstage.projections.order_queue import advance_block_label

    label = advance_block_label(operator_orders.AdvanceBlock.PREORDER_NOT_DUE)
    assert label == "Aguardando o dia da encomenda…"
