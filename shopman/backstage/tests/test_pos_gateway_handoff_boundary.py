"""Real commit callbacks: gateway capture precedes handoff and fiscal snapshot."""

from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from django.contrib.auth import get_user_model
from shopman.cashman import services as cash
from shopman.offerman.models import Product
from shopman.orderman.models import Directive, Order
from shopman.payman.models import PaymentIntent
from shopman.stockman import HoldStatus, PositionKind
from shopman.stockman.models import Position, Quant

from shopman.backstage.models import KDSInstance, KDSTicket
from shopman.backstage.tests.test_pos_link_sale_expiry_integration import POS_TRANSITIONS, _hold_rows
from shopman.shop.directives import FISCAL_EMIT_NFCE, PAYMENT_TIMEOUT
from shopman.shop.fiscal import fiscal_pool
from shopman.shop.handlers.payment_timeout import PaymentTimeoutHandler
from shopman.shop.models import Channel, Shop
from shopman.shop.services import payment, pos

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def close_counter(settings):
    settings.SHOPMAN_PAYMENT_ADAPTERS = {
        "pix": "shopman.shop.adapters.payment_mock",
        "card": "shopman.shop.adapters.payment_stripe",
        "link": "shopman.shop.adapters.payment_mock",
        "cash": None,
        "credit": None,
        "debit": None,
    }
    settings.SHOPMAN_FISCAL_ADAPTER = "shopman.backstage.tests.test_pos_counter_handoff_integration.StubFiscalBackend"
    settings.SHOPMAN_FISCAL_EMISSION_RESOLVER = "shopman.shop.fiscal_resolvers.on_request_or_tax_id,shopman.shop.fiscal_resolvers.on_requested_receipt,shopman.shop.fiscal_resolvers.eletronic_payment"
    fiscal_pool.reset()
    Shop.objects.create(name="Test", brand_name="Test")
    Channel.objects.create(
        ref="pdv",
        name="PDV",
        config={
            "confirmation": {"mode": "immediate"},
            "payment": {"method": "cash", "timing": "external"},
            "stock": {"check_on_commit": False, "allow_untracked": False, "sells_nonconforming": True},
            "lifecycle": {"transitions": POS_TRANSITIONS},
        },
    )
    operator = get_user_model().objects.create_user(username="counter")
    shift = cash.open_shift(operator=operator, float_q=0)
    Product.objects.create(sku="BREAD", name="Bread", base_price_q=100, is_published=True, is_sellable=True)
    position = Position.objects.create(ref="shelf", name="Shelf", kind=PositionKind.PHYSICAL, is_saleable=True)
    Quant.objects.create(sku="BREAD", position=position, _quantity=Decimal("10"))
    KDSInstance.objects.create(ref="picking", name="Picking", type="picking", is_active=True)

    def close(method, **overrides):
        payload = {
            "items": [{"sku": "BREAD", "name": "Bread", "qty": 2, "unit_price_q": 100}],
            "fulfillment_type": "pickup",
            "payment_method": method,
            "payment_collection": "terminal",
            "cash_shift_id": shift.pk,
            "client_request_id": f"capture-boundary-{method}",
            "fiscal_tax_id": "52998224725",
            "receipt_channels": ["print"],
            **overrides,
        }
        payload["receipt_identity_choices"] = [
            {
                "field": field,
                "value": value,
                "customer_ref": "",
                "owner_ref": "",
                "choice": "receipt_only",
                "client_request_id": payload["client_request_id"],
            }
            for field, value in [("tax_id", payload.get("fiscal_tax_id")), ("email", payload.get("receipt_email"))]
            if value
        ]
        result = pos.close_sale(channel_ref="pdv", actor="pos:counter", operator_username="counter", payload=payload)
        return Order.objects.get(ref=result.order_ref), result

    from shopman.shop.adapters import payment_stripe

    checkout_session = MagicMock(
        id="cs_test_counter", url="https://checkout.stripe.com/c/pay/cs_test_counter", payment_intent=None
    )
    sdk = MagicMock(**{"checkout.Session.create.return_value": checkout_session})
    with patch.object(payment_stripe, "_get_stripe", return_value=sdk):
        yield close
    fiscal_pool.reset()


def fiscal_rows(order):
    return Directive.objects.filter(topic=FISCAL_EMIT_NFCE, payload__order_ref=order.ref)


def assert_waiting_for_payment(order):
    assert order.status == Order.Status.ACCEPTED
    holds = _hold_rows(order)
    assert holds
    assert all(hold.status != HoldStatus.FULFILLED for hold in holds)
    assert Quant.objects.get(sku="BREAD")._quantity == Decimal("10")
    assert not KDSTicket.objects.filter(session_key=order.session_key).exists()
    assert not fiscal_rows(order).exists()


@pytest.mark.parametrize("method", ["pix", "card"])
def test_gateway_capture_releases_counter_once(close_counter, method):
    with patch("shopman.shop.services.loyalty.earn") as earn:
        order, result = close_counter(method)
        assert_waiting_for_payment(order)
        assert result.payment["intent_ref"]
        earn.assert_not_called()
        assert payment.mock_confirm(order) is True
        order.refresh_from_db()
        assert order.status == Order.Status.COMPLETED
        assert all(hold.status == HoldStatus.FULFILLED for hold in _hold_rows(order))
        assert Quant.objects.get(sku="BREAD")._quantity == Decimal("8")
        assert not KDSTicket.objects.filter(session_key=order.session_key).exists()
        assert fiscal_rows(order).get().payload["customer"]["tax_id"] == "52998224725"
        earn.assert_called_once()
        assert payment.mock_confirm(order) is False
        assert fiscal_rows(order).count() == 1
        assert Quant.objects.get(sku="BREAD")._quantity == Decimal("8")


def test_unpaid_pix_timeout_still_cancels_and_releases(close_counter):
    order, _ = close_counter("pix")
    assert_waiting_for_payment(order)
    deadline = datetime.fromisoformat(order.data["payment"]["expires_at"])
    directive = Directive.objects.get(topic=PAYMENT_TIMEOUT, payload__order_ref=order.ref)
    with patch("django.utils.timezone.now", return_value=deadline + timedelta(minutes=1)):
        PaymentTimeoutHandler().handle(message=directive, ctx={})
    order.refresh_from_db()
    assert order.status == Order.Status.CANCELLED
    assert all(hold.status == HoldStatus.RELEASED for hold in _hold_rows(order))
    assert Quant.objects.get(sku="BREAD")._quantity == Decimal("10")
    assert not fiscal_rows(order).exists()


def test_gateway_failure_does_not_release_goods_or_emit(close_counter):
    from shopman.shop.services.pos_intent import PosCommittedSaleError

    with patch.object(payment, "initiate", side_effect=TimeoutError("gateway unavailable")):
        with pytest.raises(PosCommittedSaleError) as caught:
            close_counter("pix")
    order = Order.objects.get(ref=caught.value.order_ref)
    assert_waiting_for_payment(order)
    assert caught.value.code == "sale_payment_outcome_unknown"
    assert not PaymentIntent.objects.filter(order_ref=order.ref).exists()


@pytest.mark.parametrize("method", ["cash", "credit", "debit"])
def test_physical_payment_first_fiscal_snapshot_keeps_requested_identity(close_counter, method):
    order, _ = close_counter(method, receipt_channels=["print", "email"], receipt_email="receipt@example.org")
    assert order.status == Order.Status.COMPLETED
    assert fiscal_rows(order).get().payload["customer"]["tax_id"] == "52998224725"
    assert order.data["receipt"] == {"channels": ["print", "email"], "email": "receipt@example.org"}
    assert not KDSTicket.objects.filter(session_key=order.session_key).exists()


def test_partial_capture_does_not_release_counter(close_counter):
    from shopman.payman import PaymentService

    from shopman.shop import lifecycle
    from shopman.shop.config import ChannelConfig
    from shopman.shop.services.order_helpers import customer_holds_the_goods

    order, _ = close_counter("pix")
    intent_ref = order.data["payment"]["intent_ref"]
    PaymentService.authorize(intent_ref, gateway_id="partial-capture")
    PaymentService.capture(intent_ref, amount_q=100)
    assert customer_holds_the_goods(order) is False
    lifecycle._on_accepted(order, ChannelConfig.for_channel("pdv"))
    order.refresh_from_db()
    assert_waiting_for_payment(order)


def test_future_pickup_emits_after_capture_without_accepting_or_early_handoff(close_counter):
    from django.utils import timezone

    tomorrow = (timezone.localdate() + timedelta(days=1)).isoformat()
    order, _ = close_counter("pix", delivery_date=tomorrow, customer_name="Ana", customer_phone="43999990000")
    assert order.status == Order.Status.NEW
    assert not fiscal_rows(order).exists()
    assert payment.mock_confirm(order) is True
    order.refresh_from_db()
    assert order.status == Order.Status.NEW
    assert Quant.objects.get(sku="BREAD")._quantity == Decimal("10")
    assert not KDSTicket.objects.filter(session_key=order.session_key).exists()
    assert fiscal_rows(order).get().payload["customer"]["tax_id"] == "52998224725"
