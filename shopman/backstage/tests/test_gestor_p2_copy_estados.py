"""Gestor de pedidos, beta 06/11: o que a ficha diz tem de ser o que aconteceu.

- O aviso que não se aplica ao pedido não aparece como "Não enviado".
- O cupom aparece em linha própria, com o código, e os itens a preço de tabela.
- O pronto diz quem o marcou (``test_api_order_undo``).
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from shopman.orderman.models import Directive, Order, OrderItem

from shopman.backstage.projections import notification_receipts
from shopman.backstage.projections.order_queue import build_operator_order
from shopman.shop.models import Channel, Shop

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def shop(db):
    Shop.objects.create(name="Loja")
    Channel.objects.create(ref="web", name="Loja online", config={})


def _order(ref: str, *, snapshot: dict | None = None, **extra) -> Order:
    return Order.objects.create(
        ref=ref,
        snapshot=snapshot or {},
        channel_ref="web",
        session_key=f"sk-{ref}",
        status=Order.Status.NEW,
        total_q=15500,
        data={"customer": {"name": "Ana"}, "fulfillment_type": "pickup", "payment": {"method": "cash"}, **extra},
    )


def _notice(order: Order, template: str, delivery: dict) -> Directive:
    return Directive.objects.create(
        topic="notification.send",
        status="done",
        payload={"order_ref": order.ref, "template": template, "notification_delivery": delivery},
    )


# ── Aviso que não se aplica ──────────────────────────────────────────────


def test_notice_that_does_not_apply_is_not_listed_as_not_sent():
    order = _order("P2-RECEIPT-1")
    _notice(order, "order_confirmed", {"status": "skipped", "reason": "notification_not_required"})
    _notice(order, "order_ready", {"status": "skipped", "reason": "customer_opt_out"})

    receipts = notification_receipts.build_notification_receipts(order)

    assert [r.template for r in receipts] == ["order_ready"]
    assert receipts[0].state_label == "Não enviado"
    assert receipts[0].detail == "O cliente não autorizou avisos."
    assert all("não se aplica" not in r.detail for r in receipts)


# ── Cupom em linha própria ───────────────────────────────────────────────


def test_coupon_has_its_own_line_and_items_show_the_table_price():
    """O cupom fixo de R$ 1,00 rateado no preço: Chá 150,00 → 149,27 e Água 6,00 → 5,73."""
    order = _order("P2-COUPON-1", coupon_code="bemvindo", snapshot={"pricing": {"coupon": {"code": "BEMVINDO", "discount_q": 100}}})
    coupon = {"type": "coupon", "label": "Boas-vindas", "scope": "order"}
    OrderItem.objects.create(
        order=order, line_id="1", sku="CHA", name="Chá", qty=Decimal("1"), unit_price_q=14927, line_total_q=14927,
        meta={"_list_q": 15000, "_disc": {**coupon, "amount_q": 73, "line_amount_q": 73}},
    )
    OrderItem.objects.create(
        order=order, line_id="2", sku="AGUA", name="Água", qty=Decimal("1"), unit_price_q=573, line_total_q=573,
        meta={"_list_q": 600, "_disc": {**coupon, "amount_q": 27, "line_amount_q": 27}},
    )

    detail = build_operator_order(order)

    assert [(i.name, i.unit_price_display, i.total_display) for i in detail.items] == [
        ("Chá", "R$ 150,00", "R$ 150,00"),
        ("Água", "R$ 6,00", "R$ 6,00"),
    ]
    assert [(d.kind, d.label, d.amount_display) for d in detail.discount_lines] == [
        ("coupon", "Cupom BEMVINDO", "−R$ 1,00"),
    ]


def test_line_discounts_group_by_origin_and_quantity_counts():
    order = _order("P2-COUPON-2")
    OrderItem.objects.create(
        order=order, line_id="1", sku="PAO", name="Pão", qty=Decimal("3"), unit_price_q=900, line_total_q=2700,
        meta={"_list_q": 1000, "_disc": {"type": "promotion", "label": "Happy hour", "amount_q": 100}},
    )
    OrderItem.objects.create(
        order=order, line_id="2", sku="CAFE", name="Café", qty=Decimal("1"), unit_price_q=800, line_total_q=800,
        meta={"_list_q": 800},
    )

    detail = build_operator_order(order)

    assert [(i.name, i.total_display) for i in detail.items] == [("Pão", "R$ 30,00"), ("Café", "R$ 8,00")]
    assert [(d.kind, d.label, d.amount_display) for d in detail.discount_lines] == [
        ("discount", "Happy hour", "−R$ 3,00"),
    ]


def test_order_without_discount_has_no_discount_line():
    order = _order("P2-COUPON-3")
    OrderItem.objects.create(order=order, line_id="1", sku="PAO", name="Pão", qty=Decimal("1"), unit_price_q=1000, line_total_q=1000)

    detail = build_operator_order(order)

    assert detail.discount_lines == ()
    assert detail.items[0].total_display == "R$ 10,00"
