"""Batched queue observations never become mutation authorization."""
from unittest.mock import patch

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from shopman.orderman.models import Order
from shopman.payman.models import PaymentIntent, PaymentTransaction
from shopman.payman.service import PaymentService

from shopman.shop.services import operator_orders, payment

pytestmark = pytest.mark.django_db


def test_batch_matches_live_sums_and_is_one_query():
    intents = PaymentIntent.objects.bulk_create([
        PaymentIntent(ref=f"READ-{i}", order_ref=f"ORDER-{i}", amount_q=5000, method="pix", status="refunded")
        for i in range(100)
    ])
    PaymentTransaction.objects.bulk_create([
        PaymentTransaction(intent=intent, type=kind, amount_q=amount)
        for intent in intents for kind, amount in [("capture", 5000), ("refund", 400), ("refund", 100), ("chargeback", 200)]
    ])
    with CaptureQueriesContext(connection) as queries:
        reads = PaymentService.read_many([intent.ref for intent in intents] + ["missing"])
    assert len(queries) == 1
    assert "missing" not in reads
    for intent in intents:
        assert reads[intent.ref].captured_q == PaymentService.captured_total(intent.ref)
        assert reads[intent.ref].refunded_q == PaymentService.refunded_total(intent.ref)
        assert reads[intent.ref].chargeback_q == PaymentService.chargeback_total(intent.ref)


def test_projection_snapshot_does_not_change_live_guard_after_refund():
    intent = PaymentService.settle("READ-ORDER", 1500, "cash")
    order = Order.objects.create(ref="READ-ORDER", channel_ref="web", status="accepted", total_q=1500,
        data={"payment": {"intent_ref": intent.ref, "method": "pix"}})
    reads = payment.read_payments_for([order])
    assert not operator_orders.advance_block(order, payment_reads=reads)
    PaymentService.refund(intent.ref, amount_q=1500)
    # The old observation is stable for its rendering, never attached to Order.
    assert payment.has_sufficient_captured_payment(order, payment_reads=reads)
    assert not payment.has_sufficient_captured_payment(order)
    assert operator_orders.advance_block(order) == operator_orders.AdvanceBlock.PAYMENT_NOT_CAPTURED


def test_missing_and_failed_batch_are_unknown_despite_embedded_paid():
    order = Order(ref="READ-MISSING", total_q=1500,
        data={"payment": {"intent_ref": "absent", "status": "paid"}})
    for reads in ({}, payment.read_payments_for([order])):
        assert payment.get_payment_status(order, payment_reads=reads) == "unknown"
        assert not payment.has_sufficient_captured_payment(order, payment_reads=reads)
    with patch.object(PaymentService, "read_many", side_effect=RuntimeError("synthetic read failure")):
        assert payment.read_payments_for([order]) == {}
    order.data = {"payment": {"status": "paid"}}
    assert payment.has_sufficient_captured_payment(order, payment_reads={})


def test_channel_projection_read_does_not_stale_the_next_confirmation():
    from shopman.backstage.projections.order_queue import _channel_configs_for
    from shopman.shop.config import ChannelConfig
    from shopman.shop.models import Channel, Shop

    Shop.objects.create(name="Synthetic config observation")
    channel = Channel.objects.create(ref="web", name="Web", config={"payment": {"timing": "external"}})
    order = Order(ref="READ-CONFIG", status="new", channel_ref="web", total_q=1500,
        data={"payment": {"method": "pix"}, "availability_decision": {"approved": True, "decisions": []}})
    with patch.object(ChannelConfig, "for_channel", wraps=ChannelConfig.for_channel) as resolver:
        configs = _channel_configs_for([order] * 100)
    assert resolver.call_count == 1
    assert not operator_orders.confirmation_block_reason(order, channel_config=configs["web"])
    channel.config = {"payment": {"timing": "at_commit"}}
    channel.save()
    assert operator_orders.confirmation_block_reason(order)
