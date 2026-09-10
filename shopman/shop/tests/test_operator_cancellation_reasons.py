"""Provider reads are isolated; local refusal never asserts marketplace cancellation."""
from unittest.mock import patch

import pytest
from django.contrib.auth.models import Permission, User
from shopman.orderman.models import Order

from shopman.shop.services import ifood_callbacks, operator_orders

pytestmark = pytest.mark.django_db


@pytest.fixture
def ifood_order():
    return Order.objects.create(ref="REASONS-LAB", channel_ref="ifood", external_ref="provider-lab", status="new")


@pytest.mark.parametrize("operation", ["reject", "cancel"])
@pytest.mark.parametrize("code", ["", "OLD", "FORGED"])
def test_invalid_code_never_reaches_cancellation(ifood_order, operation, code):
    with patch.object(ifood_callbacks, "fetch_cancellation_reasons", return_value=[{"cancelCodeId": "CURRENT", "description": "Indisponível"}]), patch.object(operator_orders, "cancel") as cancel:
        with pytest.raises(ValueError, match="atualmente permitido"):
            if operation == "reject":
                operator_orders.reject_order(ifood_order, reason="Motivo", actor="lab", rejected_by="operator", cancellation_code=code)
            else:
                operator_orders.cancel_order(ifood_order, reason="Motivo", actor="lab", cancellation_code=code)
        cancel.assert_not_called()
    ifood_order.refresh_from_db()
    assert ifood_order.status == "new"
    assert not ifood_order.events.exists()


@pytest.mark.parametrize("endpoint", ["cancellation-reasons", "cancel", "reject"])
def test_provider_unavailable_is_503_not_empty_or_applied(client, ifood_order, endpoint):
    user = User.objects.create_user(username="reasons-lab", is_staff=True)
    user.user_permissions.add(Permission.objects.get(content_type__app_label="shop", codename="manage_orders"))
    client.force_login(user)
    with patch.object(ifood_callbacks, "fetch_cancellation_reasons", side_effect=ifood_callbacks.IFoodCallbackError("synthetic timeout")):
        path = f"/api/v1/backstage/orders/{ifood_order.ref}/{endpoint}/"
        response = client.get(path) if endpoint == "cancellation-reasons" else client.post(path, {"reason": "Motivo", "cancellation_code": "CURRENT"}, content_type="application/json")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "cancellation_reasons_unavailable"
    ifood_order.refresh_from_db()
    assert ifood_order.status == "new"


def test_verified_empty_remains_empty_but_forbids_cancel(ifood_order):
    with patch.object(ifood_callbacks, "fetch_cancellation_reasons", return_value=[]):
        assert operator_orders.cancellation_reasons(ifood_order) == []
        with pytest.raises(ValueError):
            operator_orders.cancel_order(ifood_order, reason="Motivo", actor="lab")


def test_changed_provider_identity_during_read_refuses_mutation(ifood_order):
    def provider_read(_):
        Order.objects.filter(pk=ifood_order.pk).update(external_ref="another-order")
        return [{"cancelCodeId": "CURRENT", "description": "Motivo"}]

    with patch.object(ifood_callbacks, "fetch_cancellation_reasons", side_effect=provider_read):
        with pytest.raises(operator_orders.OrderStateConflict):
            operator_orders.cancel_order(ifood_order, reason="Motivo", actor="lab", cancellation_code="CURRENT")
    ifood_order.refresh_from_db()
    assert ifood_order.status == "new"
