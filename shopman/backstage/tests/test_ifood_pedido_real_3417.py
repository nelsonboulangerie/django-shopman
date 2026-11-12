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
