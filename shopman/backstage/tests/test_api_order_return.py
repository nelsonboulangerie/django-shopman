"""Registrar devolução no Gestor (WP-G12, decisão 2 do dono, 17/11/2026).

Itens, quantidade, motivo e o PIN de um Gerente escolhido da lista; o valor que volta
é dito antes de confirmar (a prévia). O comando é o ``ReturnService.initiate_return``.
"""

from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest
from django.contrib.auth.models import Permission
from django.urls import reverse
from shopman.orderman.models import Directive, IdempotencyKey, Order, OrderItem

from shopman.backstage.projections.order_return import return_revision
from shopman.shop.directives import RETURN_PROCESS
from shopman.shop.models import Shop

pytestmark = [pytest.mark.django_db, pytest.mark.channels("pdv")]

REGUA = {
    "delivered": ["completed", "returned"],
    "completed": ["returned", "cancelled"],
    "returned": [],
}
SIGN = "shopman.backstage.api.operations.pos_tabs_service.validate_manager_override"


@pytest.fixture
def operador(client, django_user_model):
    Shop.objects.create(name="Loja")
    user = django_user_model.objects.create_user(username="gestor-devolucao", is_staff=True)
    user.user_permissions.add(Permission.objects.get(codename="manage_orders", content_type__app_label="shop"))
    client.force_login(user)
    return user


def _order(ref: str, *, status: str = "delivered", channel_ref: str = "pdv", payment: dict | None = None) -> Order:
    order = Order.objects.create(
        ref=ref, channel_ref=channel_ref, status=status, total_q=2300,
        data={"payment": payment or {"method": "cash"}},
        snapshot={"lifecycle": {"transitions": REGUA}},
    )
    OrderItem.objects.create(order=order, line_id="L1", sku="CROIS", name="Croissant", qty=3, unit_price_q=600, line_total_q=1800)
    OrderItem.objects.create(order=order, line_id="L2", sku="CAFE", name="Café", qty=1, unit_price_q=500, line_total_q=500)
    return order


def _preview(client, order):
    return client.get(reverse("api-backstage-order-return-preview", args=[order.ref]))


def _return(client, user, order, *, key=None, base=None, **body):
    payload = {
        "expected_actor_id": user.pk,
        "base_revision": base or return_revision(order),
        "items": [{"line_id": "L1", "qty": "2"}],
        "reason": "Croissant cru por dentro",
        **body,
    }
    return client.post(
        reverse("api-backstage-order-return", args=[order.ref]), payload,
        content_type="application/json", HTTP_IDEMPOTENCY_KEY=key or str(uuid.uuid4()),
    )


def test_preview_lists_what_can_come_back_with_the_price_paid(client, operador):
    order = _order("RET-PREVIEW")

    body = _preview(client, order).json()

    assert body["allowed"] is True
    assert body["block_reason"] == ""
    lines = {line["line_id"]: line for line in body["lines"]}
    assert lines["L1"]["returnable_qty"] == "3"
    assert lines["L1"]["unit_refund_q"] == 600
    assert body["action"]["enabled"] is True
    assert body["action"]["confirmation"]["manager_approval"] is True
    assert body["action"]["payload_schema"]["base_revision"] == return_revision(order)


@pytest.mark.parametrize(
    ("status", "channel_ref", "expected"),
    [
        ("preparing", "pdv", "A devolução é para pedido entregue ou concluído."),
        ("returned", "pdv", "Este pedido já foi devolvido."),
        ("delivered", "ifood", "Pedido do iFood: a devolução e o reembolso são feitos no portal do iFood."),
    ],
)
def test_preview_says_why_the_order_does_not_take_a_return(client, operador, status, channel_ref, expected):
    order = _order(f"RET-BLOCK-{status}-{channel_ref}", status=status, channel_ref=channel_ref)

    body = _preview(client, order).json()

    assert body["allowed"] is False
    assert body["block_reason"] == expected
    assert body["action"]["enabled"] is False


def test_preview_names_where_the_money_goes(client, operador):
    order = _order("RET-PIX", payment={"method": "pix", "intent_ref": "PI-1"})

    with patch("shopman.shop.services.payment.captured_balance_q", return_value=2300):
        body = _preview(client, order).json()

    assert body["money_returns"] is True
    assert body["money_destination"] == "serão estornados ao Pix do cliente."


def test_return_asks_for_the_manager_and_writes_nothing_without_the_signature(client, operador):
    order = _order("RET-SEM-PIN")
    key = str(uuid.uuid4())

    resp = _return(client, operador, order, key=key)

    assert resp.status_code == 422, resp.content
    assert resp.json()["error"]["code"] == "manager_approval_required"
    order.refresh_from_db()
    assert "returns" not in order.data
    assert not IdempotencyKey.objects.filter(key=key).exists()


def test_signed_return_records_items_reason_and_who_signed(client, operador):
    order = _order("RET-OK")
    key = str(uuid.uuid4())

    with patch(SIGN, return_value=operador) as signature:
        resp = _return(client, operador, order, key=key, manager_approval={"username": "gerente", "pin": "SYNTHETIC-NOT-A-PIN"})

    assert resp.status_code == 200, resp.content
    assert resp.json()["outcome"] == "applied"
    assert resp.json()["refund_total_q"] == 1200
    assert signature.call_args.kwargs["action"] == "order_return"
    order.refresh_from_db()
    record = order.data["returns"][0]
    assert record["type"] == "partial"
    assert record["reason"] == "Croissant cru por dentro"
    assert record["approved_by"] == operador.get_username()
    assert record["items"] == [{"line_id": "L1", "sku": "CROIS", "qty": "2", "refund_q": 1200}]
    assert order.status == "delivered"
    assert Directive.objects.filter(topic=RETURN_PROCESS, payload__order_ref=order.ref).count() == 1
    assert "SYNTHETIC-NOT-A-PIN" not in str(IdempotencyKey.objects.get(key=key).response_body)


def test_second_return_only_takes_what_did_not_come_back_yet(client, operador):
    order = _order("RET-DUAS")
    with patch(SIGN, return_value=operador):
        assert _return(client, operador, order).status_code == 200
        order.refresh_from_db()
        assert _preview(client, order).json()["lines"][0]["returnable_qty"] == "1"

        resp = _return(client, operador, order, items=[{"line_id": "L1", "qty": "2"}])

    assert resp.status_code == 400, resp.content
    assert resp.json()["outcome"] == "not_applied"
    assert "só 1 ainda pode voltar" in resp.json()["detail"]
    order.refresh_from_db()
    assert len(order.data["returns"]) == 1


def test_returning_everything_turns_the_order_returned(client, operador):
    order = _order("RET-TOTAL")
    OrderItem.objects.create(
        order=order, line_id="FEE", sku="__DELIVERY_FEE__", name="Taxa de entrega", qty=1,
        unit_price_q=800, line_total_q=800, meta={"type": "delivery_fee"},
    )
    assert all(line["sku"] != "__DELIVERY_FEE__" for line in _preview(client, order).json()["lines"])

    with patch(SIGN, return_value=operador):
        resp = _return(client, operador, order, items=[{"line_id": "L1", "qty": "3"}, {"line_id": "L2", "qty": "1"}])

    assert resp.status_code == 200, resp.content
    order.refresh_from_db()
    assert order.status == "returned"
    assert order.data["returns"][0]["type"] == "total"
    assert order.data["returns"][0]["refund_total_q"] == 2300


def test_return_without_reason_or_items_points_at_the_field(client, operador):
    order = _order("RET-CAMPOS")

    no_reason = _return(client, operador, order, reason="  ")
    no_items = _return(client, operador, order, items=[{"line_id": "L1", "qty": "0"}])

    assert no_reason.status_code == 400
    assert no_reason.json()["field"] == "reason"
    assert no_items.status_code == 400
    assert no_items.json()["field"] == "items"


def test_stale_screen_is_refused_before_writing(client, operador):
    order = _order("RET-VELHA")
    stale = return_revision(order)
    Order.objects.filter(pk=order.pk).update(status="completed")

    with patch(SIGN, return_value=operador):
        resp = _return(client, operador, order, base=stale)

    assert resp.status_code == 409, resp.content
    order.refresh_from_db()
    assert "returns" not in order.data
