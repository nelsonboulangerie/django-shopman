"""Scheduled iFood orders can be accepted early but never prepared early."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.utils import timezone

from shopman.shop import lifecycle
from shopman.shop.config import ChannelConfig
from shopman.shop.services import ifood_ingest, ifood_orders, ifood_schedule

START = datetime(2026, 9, 14, 18, 15, tzinfo=UTC)


def _schedule():
    return {"preparation_start_at": START.isoformat(),
            "delivery_start_at": (START + timedelta(minutes=30)).isoformat(),
            "delivery_end_at": (START + timedelta(minutes=60)).isoformat()}


def _order(schedule=None, timing="SCHEDULED", channel="ifood"):
    return SimpleNamespace(
        ref="IFOOD-SCHEDULE", channel_ref=channel, status="accepted", total_q=3000,
        data={"ifood": {"order_timing": timing, "schedule": _schedule() if schedule is None else schedule},
              "payment": {"method": "external", "gateway": "ifood", "status": "pending"}},
    )


def test_mapper_preserves_root_time_and_schedule_window_as_utc():
    result = ifood_orders.map_order({
        "id": "test", "orderTiming": "SCHEDULED", "items": [],
        "preparationStartDateTime": "2026-09-14T15:15:00-03:00",
        "schedule": {"deliveryDateTimeStart": "2026-09-14T15:45:00-03:00",
                     "deliveryDateTimeEnd": "2026-09-14T16:15:00-03:00"},
        "scheduled": {"preparationStartDateTime": "2020-01-01T00:00:00Z"},
    })
    assert result["schedule"] == _schedule()


def test_documented_scheduled_fallback_without_inventing_duration():
    assert ifood_schedule.map_schedule({"scheduled": {
        "preparationStartDateTime": START.isoformat(),
        "deliveryDateTimeStart": (START + timedelta(minutes=30)).isoformat(),
        "deliveryDateTimeEnd": (START + timedelta(minutes=60)).isoformat(),
    }}) == _schedule()
    assert ifood_schedule.map_schedule({"schedule": {"deliveryDateTimeStart": START.isoformat()}})["preparation_start_at"] is None


def test_invalid_authoritative_time_is_not_replaced_by_fallback():
    result = ifood_schedule.map_schedule({
        "preparationStartDateTime": "bad-date",
        "scheduled": {"preparationStartDateTime": START.isoformat()},
    })
    assert result["preparation_start_at"] == "bad-date"
    assert "inválido" in ifood_schedule.block_reason(_order(result), now=START)


@pytest.mark.parametrize("delta,expected", [(-86400, False), (-1, False), (0, True), (1, True)])
def test_gate_uses_exact_instant_including_same_day(delta, expected):
    now = START + timedelta(seconds=delta)
    assert ifood_schedule.is_due(_order(), now=now) is expected


@pytest.mark.parametrize("value", [None, "", "not-a-date", "2026-09-14T18:15:00", "2026-99-99T99:00:00Z", 123])
def test_missing_malformed_or_naive_preparation_time_blocks_explicitly(value):
    order = _order({"preparation_start_at": value})
    assert ifood_schedule.is_due(order, now=START + timedelta(days=1)) is False
    assert "ausente ou inválido" in ifood_schedule.block_reason(order, now=START)
    assert ifood_schedule.preparation_start(order) is None


@pytest.mark.parametrize("changes", [
    {"delivery_start_at": "invalid"},
    {"delivery_end_at": None},
    {"delivery_end_at": (START - timedelta(minutes=1)).isoformat()},
    {"delivery_start_at": (START - timedelta(minutes=1)).isoformat()},
])
def test_supplied_window_must_be_valid_and_consistent(changes):
    assert ifood_schedule.is_due(_order({**_schedule(), **changes}), now=START) is False


@pytest.mark.parametrize("channel,timing", [("web", "SCHEDULED"), ("ifood", "IMMEDIATE"), ("ifood", "")])
def test_unrelated_channels_and_immediate_orders_are_unaffected(channel, timing):
    order = _order({}, channel=channel, timing=timing)
    assert ifood_schedule.is_due(order, now=START) is True
    assert ifood_schedule.block_reason(order, now=START) == ""


@pytest.mark.django_db
def test_ingest_persists_schedule_without_preventing_receipt_confirmation():
    from shopman.orderman.models import Order

    from shopman.shop.models import Channel

    Channel.objects.create(ref="ifood", name="iFood", config={"payment": {"method": "external", "timing": "external"}})
    with patch.object(ifood_ingest.order_changed, "send"):
        order = ifood_ingest.ingest({
            "order_code": "scheduled-order", "order_timing": "SCHEDULED", "schedule": _schedule(),
            "items": [{"sku": "BREAD", "qty": 1, "unit_price_q": 3000}],
        })
    assert order.data["ifood"]["schedule"] == _schedule()
    assert order.snapshot["data"]["ifood"]["schedule"] == _schedule()
    assert order.data["delivery_date"] == "2026-09-14"
    assert order.status == Order.Status.NEW
    with patch.object(ifood_schedule.timezone, "now", return_value=START - timedelta(hours=1)):
        lifecycle.ensure_payment_captured(order)
        order.transition_status(Order.Status.ACCEPTED, actor="operator")
    order.refresh_from_db()
    assert order.status == Order.Status.ACCEPTED


@pytest.mark.django_db
def test_acceptance_schedules_exact_wakeup_and_invalid_schedule_alerts():
    from shopman.orderman.models import Directive

    from shopman.backstage.models import OperatorAlert

    config = ChannelConfig(payment=ChannelConfig.Payment(method="external", timing="external"))
    order = _order()
    with (
        patch.object(ifood_schedule.timezone, "now", return_value=START - timedelta(minutes=1)),
        patch.object(lifecycle.stock, "fulfill") as fulfill,
        patch.object(lifecycle, "_dispatch_physical_work") as kitchen,
        patch.object(lifecycle.notification, "send"),
    ):
        lifecycle._on_accepted(order, config)
        lifecycle._on_paid(order, config)
        kitchen.assert_not_called()
        fulfill.assert_not_called()
    tasks = Directive.objects.filter(topic="preorder.activate")
    assert tasks.count() == 1
    assert tasks.get().available_at == START

    invalid = _order({})
    invalid.ref = "IFOOD-BAD-SCHEDULE"
    with patch.object(lifecycle.notification, "send"):
        lifecycle._on_accepted(invalid, config)
    assert not Directive.objects.filter(topic="preorder.activate", payload__order_ref=invalid.ref).exists()
    assert OperatorAlert.objects.filter(type="ifood_schedule_invalid", order_ref=invalid.ref).exists()


@pytest.mark.django_db
def test_stock_and_kitchen_wait_until_due_then_fulfill_only_once(settings):
    from shopman.orderman.models import Order
    from shopman.stockman.adapters.sku_validation import reset_sku_validator
    from shopman.stockman.models import Hold, Position, PositionKind
    from shopman.stockman.models.enums import HoldStatus
    from shopman.stockman.services.holds import StockHolds
    from shopman.stockman.services.movements import StockMovements

    from shopman.shop.models import Channel

    settings.STOCKMAN = {**getattr(settings, "STOCKMAN", {}), "SKU_VALIDATOR": "shopman.stockman.adapters.noop.NoopSkuValidator"}
    reset_sku_validator()
    try:
        Channel.objects.create(ref="ifood", name="iFood", config={"payment": {"method": "external", "timing": "external"}})
        position = Position.objects.create(ref="vitrine", name="Vitrine", kind=PositionKind.PHYSICAL, is_saleable=True)
        StockMovements.receive(quantity=Decimal("3"), sku="BREAD", position=position)
        product = SimpleNamespace(sku="BREAD", name="Pão", shelf_life_days=None)
        hold_id = StockHolds.hold(Decimal("2"), product, reference="order:IFOOD-SCHEDULE")
        hold = Hold.objects.get(pk=int(hold_id.split(":")[1]))
        data = _order().data
        data["hold_ids"] = [{"sku": "BREAD", "hold_id": hold_id, "qty": 2}]
        order = Order.objects.create(ref="IFOOD-SCHEDULE", channel_ref="ifood", status="accepted", total_q=3000, data=data)
        config = ChannelConfig.for_channel("ifood")
        with (
            patch.object(ifood_schedule.timezone, "now", return_value=START - timedelta(seconds=1)),
            patch("shopman.shop.services.kds.dispatch") as kitchen,
            patch.object(lifecycle.notification, "send"),
        ):
            lifecycle._on_accepted(order, config)
            lifecycle._on_paid(order, config)
            lifecycle._on_preparing(order, config)
            lifecycle.activate_preorder(order)
            assert lifecycle._stock_fulfill_allowed(order, config) is False
            kitchen.assert_not_called()
        hold.refresh_from_db()
        assert hold.status == HoldStatus.PENDING
        assert hold.quant.quantity == Decimal("3")
        with (
            patch.object(ifood_schedule.timezone, "now", return_value=START),
            patch("shopman.shop.services.kds.dispatch", return_value=[object()]) as kitchen,
            patch.object(lifecycle.notification, "send"),
        ):
            lifecycle.activate_preorder(order)
            lifecycle.activate_preorder(order)
        order.refresh_from_db()
        hold.refresh_from_db()
        assert order.status == Order.Status.PREPARING
        assert hold.status == HoldStatus.FULFILLED
        assert hold.quant.quantity == Decimal("1")
        assert kitchen.called
    finally:
        reset_sku_validator()


def test_delivery_date_uses_shop_timezone_and_exact_gate_overrides_delivery_day():
    schedule = {"preparation_start_at": "2026-09-15T02:30:00Z",
                "delivery_start_at": "2026-09-15T03:10:00Z",
                "delivery_end_at": "2026-09-15T03:40:00Z"}
    order = _order(schedule)
    order.data["delivery_date"] = "2026-09-15"
    with timezone.override("America/Sao_Paulo"):
        assert ifood_schedule.delivery_date_from_payload(schedule).isoformat() == "2026-09-15"
        due = datetime(2026, 9, 15, 2, 30, tzinfo=UTC)
        with patch.object(ifood_schedule.timezone, "now", return_value=due):
            assert timezone.localdate().isoformat() == "2026-09-14"
            assert lifecycle._physical_work_deferred(order) is False
        earlier_window = {**schedule, "preparation_start_at": "2026-09-15T01:00:00Z",
                          "delivery_start_at": "2026-09-15T02:00:00Z"}
        assert ifood_schedule.delivery_date_from_payload(earlier_window).isoformat() == "2026-09-14"


@pytest.mark.parametrize("schedule,early_defer", [({}, True), ({"preparation_start_at": START.isoformat()}, True), (_schedule(), False)])
def test_stock_hold_requires_authoritative_day_or_due_preparation(schedule, early_defer):
    order = _order(schedule)
    with patch.object(ifood_schedule.timezone, "now", return_value=START - timedelta(days=2)):
        assert ifood_schedule.defer_stock_hold(order) is early_defer
    with patch.object(ifood_schedule.timezone, "now", return_value=START):
        assert ifood_schedule.defer_stock_hold(order) is (not bool(schedule))


@pytest.mark.django_db
def test_no_window_defers_reservation_until_exact_activation():
    from shopman.shop.models import Channel
    Channel.objects.create(ref="ifood", name="iFood", config={"payment": {"method": "external", "timing": "external"}})
    order = _order({"preparation_start_at": START.isoformat()})
    order.snapshot = {"items": []}
    def hold_once(order):
        order.data["hold_ids"] = []
    with (
        patch.object(ifood_schedule.timezone, "now", return_value=START - timedelta(seconds=1)),
        patch.object(lifecycle.stock, "hold", side_effect=hold_once) as hold,
        patch.object(lifecycle.stock, "fulfill"),
        patch.object(lifecycle, "_dispatch_physical_work", return_value=False),
        patch.object(lifecycle.notification, "send"),
    ):
        lifecycle.activate_preorder(order)
        hold.assert_not_called()
        with patch.object(ifood_schedule.timezone, "now", return_value=START):
            lifecycle.activate_preorder(order)
            lifecycle.activate_preorder(order)
        hold.assert_called_once_with(order)


@pytest.mark.parametrize("state,retryable", [("queued", False), ("sent", False), ("error", True)])
def test_pending_cancellation_blocks_due_activation_and_physical_gates(state, retryable):
    order = _order()
    order.data["ifood_cancellation_request"] = {"state": state, "retryable": retryable}
    with (
        patch.object(ifood_schedule.timezone, "now", return_value=START),
        patch.object(lifecycle.stock, "hold") as hold,
        patch.object(lifecycle.stock, "fulfill") as fulfill,
        patch("shopman.shop.services.kds.dispatch") as kitchen,
        patch.object(lifecycle.notification, "send") as notify,
    ):
        config = ChannelConfig(payment=ChannelConfig.Payment(method="external", timing="external"))
        lifecycle.activate_preorder(order)
        lifecycle._on_preparing(order, config)
        assert lifecycle._stock_fulfill_allowed(order, config) is False
        assert lifecycle._dispatch_physical_work(order) is False
        hold.assert_not_called()
        fulfill.assert_not_called()
        kitchen.assert_not_called()
        notify.assert_not_called()


@pytest.mark.parametrize("valid_window", [True, False])
def test_commit_reserves_only_with_authoritative_delivery_day(valid_window):
    order = _order(_schedule() if valid_window else {"preparation_start_at": START.isoformat()})
    order.snapshot = {"items": [{"sku": "BREAD", "qty": 1}]}
    if valid_window:
        order.data["delivery_date"] = "2026-09-14"
    config = ChannelConfig(payment=ChannelConfig.Payment(method="external", timing="external"))
    with (
        patch.object(ifood_schedule.timezone, "now", return_value=START - timedelta(days=2)),
        patch.object(lifecycle.customer, "ensure"),
        patch.object(lifecycle.stock, "hold") as hold,
        patch.object(lifecycle.loyalty, "redeem"),
        patch.object(lifecycle.notification, "send"),
        patch.object(lifecycle, "_record_availability_decision"),
        patch.object(lifecycle, "_handle_confirmation"),
        patch.object(lifecycle, "_check_availability", return_value=True) as check,
    ):
        lifecycle._on_commit(order, config)
    assert hold.call_count == int(valid_window)
    if valid_window:
        assert hold.call_args.args[0].data["delivery_date"] == "2026-09-14"
    else:
        check.assert_not_called()


@pytest.mark.parametrize("window", [None, "bad", []])
def test_malformed_authoritative_window_container_fails_closed(window):
    schedule = ifood_schedule.map_schedule({"preparationStartDateTime": START.isoformat(), "schedule": window})
    assert ifood_schedule.is_due(_order(schedule), now=START) is False
