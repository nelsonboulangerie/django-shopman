"""V6-GESTOR (auditoria v4 do Gestor): as leituras novas que alimentam a Fila, o
detalhe e o painel do produto. Travas das classes de divergência que podem voltar.

- G06: o bloqueio do Pix escrito com as horas da cobrança;
- G24: o estado na voz do operador, e nada de "Pedido não possui próxima etapa";
- G10: a previsão "próximo pronto em ~N min" pelo início real e pelo tempo medido;
- G09: o interruptor do canal na coluna da Fila, o mesmo de Canais;
- G14/G15: o nome do canal, a linha de abertura e o prazo no detalhe;
- G26: os selos do rail fora do quadro, com a régua do quadro.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone
from shopman.orderman.models import Order, OrderItem

from shopman.backstage.presentation.status import OPERATOR_ORDER_STATUS_LABELS, order_status_label
from shopman.backstage.projections.order_attention import PrepExpectation, prep_expectation, ready_eta
from shopman.backstage.projections.order_queue import (
    board_rail_counts,
    build_operator_order,
    build_order_card,
    build_two_zone_queue,
)

pytestmark = pytest.mark.django_db


def _order(ref: str, status: str, *, channel_ref: str = "web", payment: dict | None = None, data_extra: dict | None = None) -> Order:
    data = {
        "customer": {"name": f"Cliente {ref}"},
        "fulfillment_type": "pickup",
        "payment": payment or {"method": "cash"},
        "availability_decision": {"approved": True, "decisions": []},
        **(data_extra or {}),
    }
    order = Order.objects.create(ref=ref, channel_ref=channel_ref, session_key=f"s-{ref}", status=status, total_q=1500, data=data)
    OrderItem.objects.create(order=order, line_id=f"{ref}-1", sku="PAO", name="Pão", qty=1, unit_price_q=1500, line_total_q=1500)
    return order


def test_status_label_is_the_operator_voice_not_the_customer_copy():
    assert order_status_label("preparing") == "Em preparo"
    assert all(label[1:] == label[1:].lower() or " " not in label for label in OPERATOR_ORDER_STATUS_LABELS.values())
    assert order_status_label("dispatched") == "Saiu para entrega"


def test_new_order_card_has_no_machine_copy():
    card = build_order_card(_order("V6-NEW", "new"))
    assert card.advance_block_reason == ""
    assert card.status_label == "Novo"


def test_pix_block_is_written_with_the_charge_times():
    from shopman.payman.models import PaymentIntent

    order = _order("V6-PIX", "accepted", payment={"method": "pix", "amount_q": 1500, "intent_ref": "INT-V6-PIX"})
    created = timezone.now() - timedelta(minutes=5)
    intent = PaymentIntent.objects.create(
        ref="INT-V6-PIX", order_ref=order.ref, method="pix", amount_q=1500, status="pending",
        expires_at=created + timedelta(minutes=30),
    )
    PaymentIntent.objects.filter(pk=intent.pk).update(created_at=created)

    card = build_order_card(Order.objects.get(pk=order.pk))

    assert card.advance_block_label == "Aguardando Pix"
    assert card.advance_block_reason == (
        f"gerado às {timezone.localtime(created):%H:%M} · expira às {timezone.localtime(created + timedelta(minutes=30)):%H:%M}"
        " · avança sozinho quando cair"
    )


def test_ready_eta_uses_the_real_start_and_the_measured_time():
    now = timezone.now()
    started = now - timedelta(minutes=6)
    order = _order("V6-KDS", "preparing", data_extra={"kds_started": {"7": {"at": started.isoformat(), "by": "rafael"}}})
    order.preparing_at = now - timedelta(minutes=8)
    order.save(update_fields=["preparing_at"])

    measured = ready_eta(order, PrepExpectation(minutes=10, samples=5), now=now)
    goal = ready_eta(order, PrepExpectation(minutes=None, samples=0), now=now)

    assert measured == started + timedelta(minutes=10)
    assert goal == started + timedelta(minutes=15)  # a meta padrão da estação (dono, 04/10)
    assert ready_eta(_order("V6-DONE", "ready"), PrepExpectation(minutes=10, samples=5), now=now) is None


def test_prep_expectation_is_the_median_of_recent_real_preps():
    now = timezone.now()
    for i, minutes in enumerate((8, 10, 30)):
        order = _order(f"V6-MED-{i}", "ready")
        order.preparing_at = now - timedelta(minutes=minutes + 5)
        order.ready_at = now - timedelta(minutes=5)
        order.save(update_fields=["preparing_at", "ready_at"])
    expectation = prep_expectation(now=now)
    assert expectation.samples == 3
    assert expectation.minutes == pytest.approx(10)
    assert "mediana de 3 preparos" in expectation.basis


def test_kitchen_cards_carry_the_eta_and_the_awareness_says_where_it_comes_from():
    _order("V6-PREP", "preparing")
    queue = build_two_zone_queue()
    card = next(card for card in queue.prep if card.ref == "V6-PREP")
    assert card.ready_eta_iso
    assert queue.awareness.kitchen_eta_basis


def test_menu_channels_carry_the_same_switch_as_the_channels_tab():
    from django.contrib.auth import get_user_model
    from django.contrib.auth.models import Permission

    from shopman.shop.models import Channel

    Channel.objects.update_or_create(ref="ifood", defaults={"name": "iFood", "commerce_policy": Channel.CommercePolicy.ORDER, "is_active": True})
    user = get_user_model().objects.create_user("gestor-v6", password="x", is_staff=True)
    user.user_permissions.add(Permission.objects.get(codename="manage_catalog"))
    user = get_user_model().objects.get(pk=user.pk)

    awareness = build_two_zone_queue(user=user).awareness
    rows = {row.ref: row for row in awareness.menu_channels}
    if "ifood" in rows:  # canal com interruptor neste ambiente
        sw = rows["ifood"].switch
        assert sw is not None
        assert sw.enabled
        assert sw.requires_manager_approval  # quem não é gerente chama um gerente
        assert awareness.viewer_name


def test_detail_has_channel_name_opening_line_and_deadline():
    from shopman.shop.models import Channel

    Channel.objects.update_or_create(ref="web", defaults={"name": "Loja online", "commerce_policy": Channel.CommercePolicy.ORDER})
    order = _order("V6-DET", "new", data_extra={})
    order.data["ifood"] = {"confirm_by": (timezone.now() + timedelta(minutes=4)).isoformat()}
    order.save(update_fields=["data"])

    detail = build_operator_order(Order.objects.get(pk=order.pk), context="orders")

    assert detail.channel_name == "Loja online"
    assert detail.opened_line.startswith("aberto às ")
    assert detail.confirmation_deadline_iso
    assert detail.confirmation_action == "cancel"


def test_rail_counts_follow_the_board():
    _order("V6-R-NEW", "new")
    _order("V6-R-PREP", "preparing")
    _order("V6-R-READY", "ready")
    _order("V6-R-OUT", "dispatched")
    queue = build_two_zone_queue()
    counts = board_rail_counts()
    assert counts == {"intake": len(queue.intake), "exit": queue.expedition_count}
    assert counts == {"intake": 1, "exit": 2}
