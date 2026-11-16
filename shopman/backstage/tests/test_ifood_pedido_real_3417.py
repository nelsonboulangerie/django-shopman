"""O primeiro pedido real do iFood (3417, 12/11/2026) no Gestor de pedidos.

Dois achados do dono que são da tela, não do iFood:

* a observação do item ("Embalado para presente") chegava ao ticket da cozinha
  e não ao detalhe do pedido, onde quem embala e despacha olha;
* os avisos ao cliente apareciam um a um como "Não enviado", quando no iFood
  quem avisa o cliente é o app do iFood e nenhum aviso nosso pode sair.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from shopman.orderman.models import Directive, Order, OrderItem

from shopman.backstage.projections.notification_receipts import build_notification_receipts
from shopman.backstage.projections.order_pricing import priced_items
from shopman.shop.services import notification as notification_svc

pytestmark = [pytest.mark.django_db, pytest.mark.channels("ifood", "web")]


def _order(ref: str, channel: str = "ifood") -> Order:
    return Order.objects.create(
        ref=ref, channel_ref=channel, status="preparing", total_q=4920,
        data={"fulfillment_type": "delivery"}, snapshot={"pricing": {"total_q": 4920}, "items": []},
    )


def test_observacao_do_item_chega_ao_detalhe_do_pedido():
    order = _order("IFOOD-3417-NOTA")
    OrderItem.objects.create(
        order=order, line_id="l1", sku="CAMEMBERT", name="Queijo Camembert",
        qty=Decimal("1"), unit_price_q=4800, line_total_q=4800,
        meta={"observations": "Embalado para presente", "notes": "Embalado para presente"},
    )

    items, _ = priced_items(order)

    assert items[0].notes == "Embalado para presente"


def test_item_sem_observacao_sai_vazio():
    order = _order("IFOOD-3417-SEM-NOTA")
    OrderItem.objects.create(
        order=order, line_id="l1", sku="PAO", name="Pão",
        qty=Decimal("1"), unit_price_q=1000, line_total_q=1000, meta={},
    )

    items, _ = priced_items(order)

    assert items[0].notes == ""


def _skipped_notice(order: Order) -> None:
    Directive.objects.create(
        topic=notification_svc.TOPIC,
        payload={
            "order_ref": order.ref, "template": "order_confirmed",
            "notification_delivery": {"status": "skipped", "reason": "expected_no_contact"},
        },
    )


def test_pedido_ifood_nao_lista_avisos_que_so_o_ifood_manda():
    order = _order("IFOOD-3417-AVISOS")
    _skipped_notice(order)

    assert build_notification_receipts(order) == ()


def test_outros_canais_continuam_mostrando_o_aviso_nao_enviado():
    order = _order("WEB-3417-AVISOS", channel="web")
    _skipped_notice(order)

    receipts = build_notification_receipts(order)

    assert [r.state_label for r in receipts] == ["Não enviado"]


# ── Depois do aceite, quem conduz o pedido com entregador do iFood é o iFood ──


def _courier_order(ref="IFOOD-3417-LOG", status="preparing", delivered_by="IFOOD", fulfillment="delivery"):
    return Order.objects.create(
        ref=ref, channel_ref="ifood", external_ref=f"ext-{ref}", status=status, total_q=4920,
        data={"fulfillment_type": fulfillment, "payment": {"method": "external", "status": "paid"},
              "ifood": {"delivered_by": delivered_by, "pickup_code": "6005"}},
    )


def _logistics_event(code, order, event_id=None):
    return {"id": event_id or f"ev-{code}", "code": code, "orderId": order.external_ref,
            "metadata": {"workerName": "Marcos", "workerPhone": "11999999999"}}


def test_andamento_do_entregador_vira_fato_e_selo_sem_alerta_de_portal():
    from unittest.mock import patch

    from shopman.backstage.projections import ifood
    from shopman.shop.services import ifood_events

    order = _courier_order()
    assert ifood.logistics_label(order) == ""
    with patch.object(ifood_events, "acknowledge", return_value=True), \
         patch.object(ifood_events, "_alert_unhandled_event") as alert:
        summary = ifood_events.process_events([_logistics_event("ASSIGN_DRIVER", order)])
        assert summary["failed"] == 0 and summary["acked"]
        order.refresh_from_db()
        assert ifood.logistics_label(order) == "Entregador do iFood designado: Marcos"
        # o telefone do entregador não é guardado
        assert "workerPhone" not in order.data["ifood"]["logistics"]["ASSIGN_DRIVER"]["metadata"]

        ifood_events.process_events([_logistics_event("GOING_TO_ORIGIN", order)])
        order.refresh_from_db()
        assert ifood.logistics_label(order) == "Entregador a caminho da loja"

        ifood_events.process_events([_logistics_event("DELIVERY_PICKUP_CODE_REQUESTED", order)])
        order.refresh_from_db()
        assert ifood.logistics_label(order) == "Entregador do iFood na loja"

        ifood_events.process_events([_logistics_event("DELIVERY_DROP_CODE_VALIDATION_SUCCESS", order)])
        order.refresh_from_db()
        assert ifood.logistics_label(order) == "Entregue ao cliente"
    alert.assert_not_called()


def test_selo_so_existe_com_entregador_do_ifood():
    from shopman.backstage.projections import ifood

    order = _courier_order(ref="IFOOD-3417-MCH", delivered_by="MERCHANT")
    order.data["ifood"]["logistics"] = {"ASSIGN_DRIVER": {"event_id": "x"}}
    assert ifood.logistics_label(order) == ""


def test_codigo_na_entrega_e_do_entregador_e_no_balcao_e_de_retirada():
    from shopman.backstage.projections import ifood

    assert ifood.pickup_code_label(_courier_order(ref="IFOOD-3417-D")) == "Código do entregador · 6005"
    assert ifood.pickup_code_label(_courier_order(ref="IFOOD-3417-T", fulfillment="pickup")) == "Código de retirada · 6005"


def test_pronto_e_saiu_ficam_no_menu_quando_o_entregador_e_do_ifood():
    from django.contrib.auth import get_user_model

    from shopman.shop.services import operator_orders

    user = get_user_model().objects.create_superuser("gestor3417", "g@x.com", "x")
    ifood_courier = _courier_order(ref="IFOOD-3417-MENU")
    own = _courier_order(ref="IFOOD-3417-OWN", delivered_by="MERCHANT")

    def advance_priority(order):
        actions = operator_orders.operational_actions(order, user=user)
        return next(a.priority for a in actions if a.ref == "advance")

    assert advance_priority(ifood_courier) == "menu"
    assert advance_priority(own) == "primary"
    Order.objects.filter(pk=ifood_courier.pk).update(status="dispatched")
    ifood_courier.refresh_from_db()
    assert advance_priority(ifood_courier) == "menu"  # "Marcar como entregue" é do iFood


def test_linha_do_tempo_mostra_o_que_o_ifood_conduz_na_ordem_da_hora():
    """O andamento do entregador e o encerramento lá entram no histórico (dono, 14/11)."""
    from datetime import timedelta

    from django.utils import timezone

    from shopman.backstage.projections.order_queue import _build_timeline

    order = _courier_order(ref="IFOOD-3417-TL")
    accepted = order.events.order_by("seq").last()
    base = (accepted.created_at if accepted else timezone.now()) + timedelta(minutes=1)
    order.data["ifood"]["logistics"] = {
        "ASSIGN_DRIVER": {"observed_at": base.isoformat(), "metadata": {"workerName": "Marcos"}},
        "ARRIVED_AT_ORIGIN": {"observed_at": (base + timedelta(minutes=5)).isoformat()},
        # O mesmo passo dito de dois jeitos aparece uma vez só.
        "DELIVERY_PICKUP_CODE_REQUESTED": {"observed_at": (base + timedelta(minutes=6)).isoformat()},
        "COLLECTED": {"observed_at": (base + timedelta(minutes=8)).isoformat()},
        "GOING_TO_ORIGIN": {},  # sem hora: fica de fora
    }
    order.data["ifood"]["remote_concluded"] = {"observed_at": (base + timedelta(minutes=30)).isoformat()}
    order.save(update_fields=["data"])

    ifood_lines = [(e.label, e.actor, e.detail) for e in _build_timeline(order) if e.event_type == "ifood_fact"]

    assert ifood_lines == [
        ("Entregador do iFood designado", "iFood", "Marcos"),
        ("Entregador do iFood na loja", "iFood", ""),
        ("Saiu com o entregador do iFood", "iFood", ""),
        ("Concluído no iFood", "iFood", ""),
    ]


def test_linha_do_tempo_de_outro_canal_nao_ganha_fato_do_ifood():
    from shopman.backstage.projections.order_queue import _build_timeline

    order = _order("WEB-3417-TL", channel="web")
    assert not [e for e in _build_timeline(order) if e.event_type == "ifood_fact"]
