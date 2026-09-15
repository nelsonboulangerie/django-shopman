"""Imported payment evidence must not become a second local collection flow."""

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from shopman.shop import lifecycle
from shopman.shop.config import ChannelConfig
from shopman.shop.services import ifood_ingest, ifood_orders, payment


@pytest.mark.parametrize("raw,expected", [
    ({"prepaid": 30, "pending": 0}, "paid"),
    ({"prepaid": 0, "pending": 30, "methods": [
        {"method": "CASH", "type": "OFFLINE", "prepaid": False, "value": 30,
         "cash": {"changeFor": 50}},
    ]}, "pending"),
    ({"prepaid": 0, "pending": 30, "methods": [
        {"method": "CREDIT", "type": "OFFLINE", "prepaid": False, "value": 30,
         "card": {"brand": "VISA"}},
    ]}, "pending"),
    ({"prepaid": 10, "pending": 20}, "pending"),
    ({"prepaid": 10, "pending": 0}, "unknown"),
    ({}, "unknown"),
    ({"prepaid": 30, "pending": 0, "methods": [
        {"type": "OFFLINE", "prepaid": False, "value": 30},
    ]}, "pending"),
])
@pytest.mark.parametrize("delivered_by", ["MERCHANT", "IFOOD", ""])
@pytest.mark.django_db
def test_ingest_preserves_settlement_without_manufacturing_payment(raw, expected, delivered_by):
    from shopman.shop.models import Channel

    Channel.objects.get_or_create(ref="ifood", defaults={"name": "iFood"})
    payload = ifood_orders.map_order({
        "id": "payment-test", "orderType": "DELIVERY",
        "total": {"orderAmount": 30}, "payments": raw,
        "delivery": {"deliveredBy": delivered_by},
        "items": [{"id": "item", "externalCode": "BREAD", "quantity": 1,
                   "unitPrice": 30, "totalPrice": 30}],
    })
    # Lifecycle coordination is tested separately below; isolate ingest writes.
    with patch.object(ifood_ingest.order_changed, "send"):
        order = ifood_ingest.ingest(payload)
    assert payment.get_payment_status(order) == expected
    assert payment.has_sufficient_captured_payment(order) is (expected == "paid")
    assert order.data["payment"] == {"method": "external", "gateway": "ifood", "status": expected}
    assert order.data["ifood"]["delivered_by"] == delivered_by
    assert order.data["ifood"]["payments"] == payload["payments"]


def test_mixed_methods_preserve_cash_base_and_card_brand_independently():
    mapped = ifood_orders._map_payments({
        "prepaid": 10, "pending": 20,
        "methods": [
            {"method": "CREDIT", "type": "ONLINE", "prepaid": True, "value": 10,
             "card": {"brand": "MASTERCARD"}},
            {"method": "CASH", "type": "OFFLINE", "prepaid": False, "value": 20,
             "cash": {"changeFor": 50}},
        ],
    })
    card, cash = mapped["methods"]
    assert card["brand"] == "MASTERCARD"
    assert card["change_for_q"] == 0
    assert cash["change_for_q"] == 5000
    assert cash["value_q"] == 2000  # cash change is 30, not 50 minus the whole order
    assert (mapped["prepaid_q"], mapped["pending_q"]) == (1000, 2000)


def test_missing_prepaid_flag_is_not_rewritten_as_explicit_unpaid_evidence():
    mapped = ifood_orders._map_payments({"methods": [{"method": "CREDIT", "value": 30}]})
    assert mapped["methods"][0]["prepaid"] is None
    assert ifood_ingest.payment_status_from_payload(mapped, 3000) == "unknown"


def _external_config():
    return ChannelConfig(
        payment=ChannelConfig.Payment(method="external", timing="external"),
        fulfillment=ChannelConfig.Fulfillment(prep_start="auto"),
    )


@pytest.mark.parametrize("status", ["paid", "pending", "unknown"])
def test_acceptance_prepares_and_consumes_stock_without_collecting_again(status):
    order = SimpleNamespace(
        ref="IFOOD-PAYMENT", channel_ref="ifood", status="accepted", total_q=3000,
        data={"payment": {"method": "external", "gateway": "ifood", "status": status}},
    )
    config = _external_config()
    with (
        patch.object(lifecycle.ChannelConfig, "for_channel", return_value=config),
        patch.object(lifecycle, "_physical_work_deferred", return_value=False),
        patch.object(lifecycle, "_counter_handoff", return_value=False),
        patch.object(lifecycle, "_dispatch_physical_work", return_value=True) as kitchen,
        patch.object(lifecycle, "_mark_preparing_after_physical_work_dispatch") as preparing,
        patch.object(lifecycle.stock, "fulfill") as fulfill,
        patch.object(lifecycle.notification, "send"),
        patch.object(payment, "initiate") as initiate,
        patch.object(payment, "capture") as capture,
    ):
        lifecycle.ensure_payment_captured(order)
        lifecycle._on_accepted(order, config)
    kitchen.assert_called_once_with(order)
    preparing.assert_called_once_with(order)
    fulfill.assert_called_once_with(order)
    initiate.assert_not_called()
    capture.assert_not_called()
    assert payment.get_payment_status(order) == status


@pytest.mark.parametrize("channel,gateway,method,timing", [
    ("other-marketplace", "ifood", "external", "external"),
    ("ifood", "other", "external", "external"),
    ("ifood", "ifood", "link", "external"),
    ("ifood", "ifood", "external", "at_commit"),
])
def test_ifood_stock_exception_does_not_relax_other_payment_policies(channel, gateway, method, timing):
    order = SimpleNamespace(
        channel_ref=channel, total_q=3000,
        data={"payment": {"method": method, "gateway": gateway, "status": "pending"}},
    )
    config = ChannelConfig(payment=ChannelConfig.Payment(method="external", timing=timing))
    assert lifecycle._stock_fulfill_allowed(order, config) is False
