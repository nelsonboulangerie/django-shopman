"""Backstage SSE publisher tests.

Emits are deferred to ``transaction.on_commit`` (ADR-016), so each mutation
runs inside ``django_capture_on_commit_callbacks(execute=True)``.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from unittest.mock import patch

import pytest
from shopman.craftsman import craft
from shopman.craftsman.models import Recipe
from shopman.orderman.models import Order

from shopman.backstage.models import OperatorAlert
from shopman.shop.models import Channel, Shop


@pytest.fixture
def channel(db):
    return Channel.objects.create(ref="web", name="Web", is_active=True)


@pytest.fixture
def recipe(db):
    return Recipe.objects.create(
        ref="sse-prod-v1",
        name="SSE Produto",
        output_sku="SSE-PROD",
        batch_size=Decimal("10"),
    )


@pytest.mark.django_db
@patch("django_eventstream.send_event")
def test_order_change_publishes_backstage_orders_event(
    mock_send, channel, django_capture_on_commit_callbacks,
):
    order = Order.objects.create(ref="SSE-ORD-1", channel_ref=channel.ref, status=Order.Status.NEW, total_q=1000)

    with django_capture_on_commit_callbacks(execute=True):
        order.transition_status(Order.Status.ACCEPTED, actor="test")

    assert any(
        call.args[0] == "backstage-orders-main"
        and call.args[1] == "backstage-orders-update"
        and call.args[2]["ref"] == "SSE-ORD-1"
        for call in mock_send.call_args_list
    )


@pytest.mark.django_db
@patch("django_eventstream.send_event")
def test_production_change_publishes_backstage_production_event(
    mock_send, recipe, django_capture_on_commit_callbacks,
):
    with django_capture_on_commit_callbacks(execute=True):
        work_order = craft.plan(recipe, 10, date=date.today(), position_ref="forno")

    assert any(
        call.args[0] == "backstage-production-main"
        and call.args[1] == "backstage-production-update"
        and call.args[2]["ref"] == work_order.ref
        for call in mock_send.call_args_list
    )


@pytest.mark.django_db
@patch("django_eventstream.send_event")
def test_operator_alert_publishes_backstage_alerts_event(
    mock_send, django_capture_on_commit_callbacks,
):
    with django_capture_on_commit_callbacks(execute=True):
        alert = OperatorAlert.objects.create(
            type="production_late",
            severity="warning",
            message="Produção atrasada",
        )

    assert any(
        call.args[0] == "backstage-alerts-main"
        and call.args[1] == "backstage-alerts-update"
        and call.args[2]["id"] == alert.pk
        for call in mock_send.call_args_list
    )


@pytest.mark.django_db
@patch("django_eventstream.send_event")
def test_order_change_publishes_shop_scoped_backstage_event(
    mock_send, django_capture_on_commit_callbacks,
):
    shop = Shop.objects.create(name="SSE Loja")
    channel = Channel.objects.create(ref="web-scoped", name="Web Scoped", shop=shop, is_active=True)
    order = Order.objects.create(
        ref="SSE-ORD-SCOPED",
        channel_ref=channel.ref,
        status=Order.Status.NEW,
        total_q=1000,
    )

    with django_capture_on_commit_callbacks(execute=True):
        order.transition_status(Order.Status.ACCEPTED, actor="test")

    channels = [call.args[0] for call in mock_send.call_args_list]
    assert "backstage-orders-main" in channels
    assert f"backstage-orders-shop-{shop.pk}" in channels


@pytest.mark.django_db
@patch("django_eventstream.send_event")
def test_production_change_publishes_shop_scoped_backstage_event(
    mock_send, recipe, django_capture_on_commit_callbacks,
):
    shop = Shop.objects.create(name="SSE Producao")

    with django_capture_on_commit_callbacks(execute=True):
        craft.plan(recipe, 10, date=date.today(), position_ref="forno")

    channels = [call.args[0] for call in mock_send.call_args_list]
    assert "backstage-production-main" in channels
    assert f"backstage-production-shop-{shop.pk}" in channels


@pytest.mark.django_db
@patch("django_eventstream.send_event")
def test_note_commit_invalidates_operator_projection_without_exposing_note(mock_send, channel, django_capture_on_commit_callbacks):
    from shopman.shop.services.operator_orders import save_kitchen_note
    order = Order.objects.create(ref="SSE-NOTE", channel_ref=channel.ref, status="accepted")
    with django_capture_on_commit_callbacks(execute=True):
        save_kitchen_note(order, notes="private preparation text", actor="operator")
    calls = [call for call in mock_send.call_args_list if call.args[1] == "backstage-orders-update"]
    assert len(calls) == 1
    assert calls[0].args[2] == {"ref": "SSE-NOTE", "kind": "kitchen_note_changed"}
    assert not any(call.args[0] == "order-SSE-NOTE" for call in mock_send.call_args_list)
    assert order.events.get(type="kitchen_note_changed").actor == "operator"


@pytest.mark.django_db
@patch("django_eventstream.send_event")
def test_rolled_back_note_never_publishes_context(mock_send, channel, django_capture_on_commit_callbacks):
    from django.db import transaction

    from shopman.shop.services.operator_orders import save_kitchen_note
    order = Order.objects.create(ref="SSE-NOTE-ROLLBACK", channel_ref=channel.ref, status="accepted")
    with django_capture_on_commit_callbacks(execute=True):
        with transaction.atomic():
            save_kitchen_note(order, notes="must roll back")
            transaction.set_rollback(True)
    assert not any(call.args[1] == "backstage-orders-update" for call in mock_send.call_args_list)
    assert not order.events.filter(type="kitchen_note_changed").exists()


@pytest.mark.django_db
@patch("django_eventstream.send_event")
def test_resolved_operator_alert_refreshes_other_surfaces(mock_send, django_capture_on_commit_callbacks):
    from django.utils import timezone

    alert = OperatorAlert.objects.create(type="cash_change_requested", message="Troco solicitado")
    with django_capture_on_commit_callbacks(execute=True):
        alert.resolved_at = timezone.now()
        alert.save(update_fields=["resolved_at"])
    assert any(
        call.args[0] == "backstage-alerts-main"
        and call.args[1] == "backstage-alerts-update"
        and call.args[2]["id"] == alert.pk
        for call in mock_send.call_args_list
    )
