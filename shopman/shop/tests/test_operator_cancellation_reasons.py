"""Motivo da casa → código do iFood: fixo, conferido contra a lista do pedido.

Dono, 07/11/2026: UMA lista de motivos para recusar e cancelar, em qualquer canal.
No iFood, o ``cancellationCode`` sai do motivo (``DEFAULT_REASON_CODES``) e é
conferido contra ``GET cancellationReasons`` do pedido antes de mexer nele.
"""
from unittest.mock import patch

import pytest
from django.contrib.auth.models import Permission, User
from shopman.orderman.models import Order

from shopman.shop.policies.ifood_cancel_reasons import offered_on_ifood
from shopman.shop.services import cancel_reasons, ifood_callbacks, operator_orders

pytestmark = pytest.mark.django_db


@pytest.fixture
def ifood_order():
    return Order.objects.create(ref="REASONS-LAB", channel_ref="ifood", external_ref="provider-lab", status="new")


def test_reason_codes_are_fixed_and_cover_every_reason_offered_on_ifood():
    assert ifood_callbacks.DEFAULT_REASON_CODES == {
        "out_of_stock": "503",
        "cannot_deliver": "504",
        "high_demand": "509",
        "duplicate_order": "502",
        "store_closing": "508",
        "other": "501",
    }
    offered = {r.key for r in cancel_reasons.OPERATOR_CANCEL_REASONS if offered_on_ifood(r.key)}
    assert offered == set(ifood_callbacks.DEFAULT_REASON_CODES)
    assert ifood_callbacks.resolve_cancellation_code("customer_request") == ""


@pytest.mark.parametrize("operation", ["reject", "cancel"])
@pytest.mark.parametrize("reason_key", ["", "customer_request", "payment_not_confirmed", "inventado"])
def test_reason_outside_the_ifood_list_never_reaches_cancellation(ifood_order, operation, reason_key):
    with patch.object(operator_orders, "cancel") as cancel:
        with pytest.raises(ValueError):
            if operation == "reject":
                operator_orders.reject_order(ifood_order, reason="Motivo", actor="lab", rejected_by="operator", reason_key=reason_key)
            else:
                operator_orders.cancel_order(ifood_order, reason="Motivo", actor="lab", reason_key=reason_key)
        cancel.assert_not_called()
    ifood_order.refresh_from_db()
    assert ifood_order.status == "new"


@pytest.mark.parametrize("operation", ["reject", "cancel"])
def test_code_not_offered_for_this_order_never_reaches_cancellation(ifood_order, operation):
    offered = [{"cancelCodeId": "999", "description": "Outro código"}]
    with patch.object(ifood_callbacks, "fetch_cancellation_reasons", return_value=offered), patch.object(operator_orders, "cancel") as cancel:
        with pytest.raises(ValueError, match="atualmente permitido"):
            if operation == "reject":
                operator_orders.reject_order(ifood_order, reason="Acabou um item", actor="lab", rejected_by="operator", reason_key="out_of_stock")
            else:
                operator_orders.cancel_order(ifood_order, reason="Acabou um item", actor="lab", reason_key="out_of_stock")
        cancel.assert_not_called()


@pytest.mark.parametrize("operation", ["reject", "cancel"])
def test_the_code_of_the_reason_rides_the_cancellation(ifood_order, operation):
    offered = [{"cancelCodeId": "509", "description": "Alta demanda"}]
    with patch.object(ifood_callbacks, "fetch_cancellation_reasons", return_value=offered), patch.object(operator_orders, "cancel", return_value=True) as cancel:
        if operation == "reject":
            operator_orders.reject_order(ifood_order, reason="Muitos pedidos agora", actor="lab", rejected_by="operator", reason_key="high_demand")
        else:
            operator_orders.cancel_order(ifood_order, reason="Muitos pedidos agora", actor="lab", reason_key="high_demand")
    extra = cancel.call_args.kwargs["extra_data"]
    assert extra["ifood_cancellation_code"] == "509"
    assert extra["cancellation_reason_key"] == "high_demand"


@pytest.mark.parametrize("endpoint", ["cancel", "reject"])
def test_provider_unavailable_is_503_not_applied(client, ifood_order, endpoint):
    user = User.objects.create_user(username="reasons-lab", is_staff=True)
    user.user_permissions.add(Permission.objects.get(content_type__app_label="shop", codename="manage_orders"))
    client.force_login(user)
    with patch.object(ifood_callbacks, "fetch_cancellation_reasons", side_effect=ifood_callbacks.IFoodCallbackError("synthetic timeout")):
        path = f"/api/v1/backstage/orders/{ifood_order.ref}/{endpoint}/"
        body = {
            "reason_key": "out_of_stock",
            "expected_actor_id": user.pk,
            "base_revision": operator_orders.operational_revision(ifood_order),
            "idempotency_key": f"provider-unavailable-{endpoint}",
        }
        response = client.post(path, body, content_type="application/json")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "cancellation_reasons_unavailable"
    ifood_order.refresh_from_db()
    assert ifood_order.status == "new"


def test_changed_provider_identity_during_read_refuses_mutation(ifood_order):
    def provider_read(_):
        Order.objects.filter(pk=ifood_order.pk).update(external_ref="another-order")
        return [{"cancelCodeId": "503", "description": "Motivo"}]

    with patch.object(ifood_callbacks, "fetch_cancellation_reasons", side_effect=provider_read):
        with pytest.raises(operator_orders.OrderStateConflict):
            operator_orders.cancel_order(ifood_order, reason="Acabou um item", actor="lab", reason_key="out_of_stock")
    ifood_order.refresh_from_db()
    assert ifood_order.status == "new"
