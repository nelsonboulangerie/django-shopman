"""Balcão imediato e encomenda identificada têm contratos distintos."""
from __future__ import annotations

import pytest
from django.utils import timezone
from shopman.guestman.models import Customer
from shopman.orderman.models import Order

from shopman.backstage.projections.pos import build_open_tab
from shopman.shop.services import pos
from shopman.shop.services.pos_intent import PosIntentError, parse_pos_sale_intent
from shopman.shop.tests.test_pos_scheduled_order import _close, _payload, balcao  # noqa: F401

pytestmark = pytest.mark.django_db


def order_payload(**extra):
    customer, _ = Customer.objects.get_or_create(ref="selected", defaults={"first_name": "Maria"})
    return {
        "sales_mode": "order", "customer_ref": customer.ref,
        "fulfillment_type": "pickup", "delivery_date": timezone.localdate().isoformat(),
        "items": [{"sku": "CR", "qty": 1, "unit_price_q": 900}], **extra,
    }


@pytest.mark.parametrize("missing,code", [
    ("customer_ref", "order_customer_required"),
    ("fulfillment_type", "order_fulfillment_required"),
    ("delivery_date", "order_date_required"),
])
def test_order_requires_wizard_before_items(missing, code):
    payload = order_payload()
    payload.pop(missing)
    with pytest.raises(PosIntentError) as error:
        parse_pos_sale_intent(payload, for_commit=False)
    assert error.value.code == code


@pytest.mark.parametrize("mode", ["remote", "", [], {}])
def test_invalid_mode_is_recoverable(mode):
    with pytest.raises(PosIntentError) as error:
        parse_pos_sale_intent({"sales_mode": mode, "items": []}, for_commit=False)
    assert error.value.code == "invalid_sales_mode"


@pytest.mark.parametrize("extra", [{"fulfillment_type": "delivery"}, {"delivery_date": "2026-12-01"}, {"delivery_time_slot": "10:00"}])
def test_counter_refuses_delivery_or_schedule(extra):
    with pytest.raises(PosIntentError) as error:
        parse_pos_sale_intent({"sales_mode": "counter", "items": [], **extra}, for_commit=False)
    assert error.value.code == "counter_requires_immediate_pickup"


def test_inactive_and_unknown_customer_cannot_start_order():
    payload = order_payload()
    Customer.objects.filter(ref="selected").update(is_active=False)
    for ref in ("selected", "missing"):
        with pytest.raises(PosIntentError) as error:
            parse_pos_sale_intent({**payload, "customer_ref": ref}, for_commit=False)
        assert error.value.code == "order_customer_invalid"


def test_empty_order_wizard_persists_and_omission_cannot_bypass_mode(balcao):  # noqa: F811
    operator, _ = balcao
    session = pos.open_pos_tab(channel_ref="pdv", tab_ref="WIZARD", actor="test", operator_username=operator.username)
    identity = {"tab_ref": "WIZARD", "tab_session_key": session.session_key}
    pos.save_pos_tab(channel_ref="pdv", payload={**identity, "sales_mode": "order", "items": []},
                     actor="test", operator_username=operator.username)
    session.refresh_from_db()
    projection = build_open_tab(session)
    assert projection["sales_mode"] == "order"
    assert projection["fulfillment_type"] == ""
    assert projection["items"] == []
    with pytest.raises(PosIntentError) as error:
        pos.save_pos_tab(channel_ref="pdv", payload={**identity, "items": [{"sku": "CR", "qty": 1, "unit_price_q": 900}]},
                         actor="test", operator_username=operator.username)
    assert error.value.code == "order_customer_required"
    session.refresh_from_db()
    assert not session.items


@pytest.mark.parametrize("mode", ["counter", "order"])
def test_direct_close_preserves_mode_in_order(balcao, mode):  # noqa: F811
    operator, shift = balcao
    extra = order_payload() if mode == "order" else {"sales_mode": "counter", "customer_name": ""}
    result = _close(operator, _payload(shift, client_request_id=f"mode-{mode}", **extra))
    order = Order.objects.get(ref=result.order_ref)
    assert order.data["pos"]["sales_mode"] == mode
    if mode == "order":
        assert order.data["customer"]["ref"] == "selected"
        assert order.data["delivery_date"] == timezone.localdate().isoformat()


def test_order_tab_save_roundtrip_and_close(balcao):  # noqa: F811
    operator, shift = balcao
    session = pos.open_pos_tab(channel_ref="pdv", tab_ref="ORDER", actor="test", operator_username=operator.username)
    payload = _payload(shift, client_request_id="order-tab", **order_payload(),
                       tab_ref="ORDER", tab_session_key=session.session_key)
    pos.save_pos_tab(channel_ref="pdv", payload=payload, actor="test", operator_username=operator.username)
    session.refresh_from_db()
    projection = build_open_tab(session)
    assert projection["sales_mode"] == "order"
    assert projection["customer_ref"] == "selected"
    assert projection["delivery_date"] == timezone.localdate().isoformat()
    result = _close(operator, payload)
    assert Order.objects.get(ref=result.order_ref).data["pos"]["sales_mode"] == "order"


def test_transfer_cannot_add_lines_to_incomplete_order(balcao):  # noqa: F811
    operator, _ = balcao
    sessions = [pos.open_pos_tab(channel_ref="pdv", tab_ref=ref, actor="test", operator_username=operator.username)
                for ref in ("SOURCE", "TARGET")]
    source, target = sessions
    pos.save_pos_tab(channel_ref="pdv", payload={**order_payload(), "tab_ref": "SOURCE", "tab_session_key": source.session_key},
                     actor="test", operator_username=operator.username)
    pos.save_pos_tab(channel_ref="pdv", payload={"sales_mode": "order", "items": [], "tab_ref": "TARGET", "tab_session_key": target.session_key},
                     actor="test", operator_username=operator.username)
    source.refresh_from_db()
    with pytest.raises(PosIntentError) as error:
        pos.move_pos_tab_lines(channel_ref="pdv", from_session_key=source.session_key, to_session_key=target.session_key,
                               line_ids=[source.items[0]["line_id"]], actor="test", operator_username=operator.username)
    assert error.value.code == "order_customer_required"
    target.refresh_from_db()
    assert target.items == []
