"""Recovery of real post-commit failures never trusts the retry's payment data."""

from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from shopman.cashman import Terminal
from shopman.cashman import services as cash
from shopman.orderman.models import IdempotencyKey, Order
from shopman.payman.models import PaymentIntent

from shopman.shop.adapters import payment_mock
from shopman.shop.services import pos
from shopman.shop.services.pos_intent import PosCommittedSaleError
from shopman.shop.services.pos_sale_recovery import SCOPE
from shopman.shop.tests.test_pos_cash_ledger import _Counter

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def counter(settings):
    settings.SHOPMAN_PAYMENT_ADAPTERS = {"pix": "shopman.shop.adapters.payment_mock", "cash": None}
    return _Counter()


def assert_created_error(error, order):
    assert error.order_ref == order.ref
    assert error.as_dict()["order_created"] is True
    assert error.status == 409


def test_retry_repairs_local_settlement_in_original_drawer(counter):
    with patch.object(pos, "_record_sale", side_effect=RuntimeError("ledger disconnected")):
        with pytest.raises(PosCommittedSaleError) as caught:
            counter.close(client_request_id="local-recovery")
    order = Order.objects.get()
    assert_created_error(caught.value, order)
    assert not PaymentIntent.objects.filter(order_ref=order.ref).exists()
    assert not counter.sale_lines()
    other = get_user_model().objects.create_user(username="other")
    other_shift = cash.open_shift(operator=other, terminal=Terminal.objects.create(ref="other-terminal"), float_q=0)
    recovered = counter.close(client_request_id="local-recovery", shift=other_shift, operator=other)
    assert recovered.order_ref == order.ref
    (entry,) = counter.sale_lines()
    assert entry.operator == counter.operator
    assert entry.amount_q == 1200
    assert not counter.sale_lines(other_shift)
    assert PaymentIntent.objects.filter(order_ref=order.ref).count() == 1
    assert counter.close(client_request_id="local-recovery").order_ref == order.ref
    assert len(counter.sale_lines()) == 1
    assert Order.objects.count() == 1


def test_retry_after_commit_before_gateway_starts_initial_charge_once(counter):
    with patch.object(pos, "_mark_tab_committed", side_effect=RuntimeError("process interrupted")):
        with pytest.raises(PosCommittedSaleError) as caught:
            counter.close(client_request_id="before-gateway", payment_method="pix")
    order = Order.objects.get()
    assert_created_error(caught.value, order)
    assert not PaymentIntent.objects.filter(order_ref=order.ref).exists()
    with patch.object(payment_mock, "create_intent", wraps=payment_mock.create_intent) as create:
        recovered = counter.close(client_request_id="before-gateway", payment_method="cash")
        replay = counter.close(client_request_id="before-gateway", payment_method="cash")
    assert recovered.order_ref == replay.order_ref == order.ref
    assert recovered.payment["method"] == "pix"
    create.assert_called_once()
    assert counter.sale_lines()[0].amount_q == 0


def test_retry_after_gateway_before_ledger_reuses_intent_without_network(counter):
    with patch.object(pos, "_record_sale", side_effect=RuntimeError("ledger disconnected")):
        with pytest.raises(PosCommittedSaleError) as caught:
            counter.close(client_request_id="after-gateway", payment_method="pix")
    order = Order.objects.get()
    assert_created_error(caught.value, order)
    intent = PaymentIntent.objects.get(order_ref=order.ref)
    with patch.object(payment_mock, "create_intent", side_effect=AssertionError("must not contact gateway")):
        result = counter.close(client_request_id="after-gateway", payment_method="pix")
    assert result.order_ref == order.ref
    assert result.payment["intent_ref"] == intent.ref
    assert counter.sale_lines()[0].payment_ref == intent.ref
    assert PaymentIntent.objects.filter(order_ref=order.ref).count() == 1


def test_unknown_gateway_outcome_is_not_retried_or_reported_as_success(counter):
    with patch.object(payment_mock, "create_intent", side_effect=TimeoutError("response lost")) as create:
        with pytest.raises(PosCommittedSaleError) as first:
            counter.close(client_request_id="unknown-gateway", payment_method="pix")
        with pytest.raises(PosCommittedSaleError) as replay:
            counter.close(client_request_id="unknown-gateway", payment_method="pix")
    order = Order.objects.get()
    assert_created_error(first.value, order)
    assert_created_error(replay.value, order)
    assert replay.value.code == "sale_payment_outcome_unknown"
    create.assert_called_once()
    assert not PaymentIntent.objects.filter(order_ref=order.ref).exists()
    assert IdempotencyKey.objects.get(scope=SCOPE, key=order.ref).status != "done"


def test_closed_original_drawer_does_not_move_recovery_to_a_new_shift(counter):
    with patch.object(pos, "_record_sale", side_effect=RuntimeError("ledger disconnected")):
        with pytest.raises(PosCommittedSaleError):
            counter.close(client_request_id="closed-original")
    order = Order.objects.get()
    cash.close_shift(counter.shift, counted_q=10000, actor=counter.operator)
    newer = cash.open_shift(operator=counter.operator, terminal=counter.shift.terminal, float_q=0)
    with pytest.raises(PosCommittedSaleError) as caught:
        counter.close(client_request_id="closed-original", shift=newer)
    assert_created_error(caught.value, order)
    assert caught.value.code == "cash_shift_closed_mid_sale"
    assert not counter.sale_lines(newer)
    assert not counter.sale_lines()


def test_lost_order_intent_pointer_is_restored_from_payman(counter):
    from shopman.shop.services import payment

    with patch.object(payment, "_persist_intent", side_effect=RuntimeError("pointer write lost")):
        with pytest.raises(PosCommittedSaleError):
            counter.close(client_request_id="lost-pointer", payment_method="pix")
    order = Order.objects.get()
    intent = PaymentIntent.objects.get(order_ref=order.ref)
    assert not order.data["payment"].get("intent_ref")
    with patch.object(payment_mock, "create_intent", side_effect=AssertionError("must not contact gateway")):
        recovered = counter.close(client_request_id="lost-pointer", payment_method="pix")
    assert recovered.payment["intent_ref"] == intent.ref
    order.refresh_from_db()
    assert order.data["payment"]["intent_ref"] == intent.ref
    assert counter.sale_lines()[0].payment_ref == intent.ref


def test_lost_gateway_settlement_receipt_does_not_duplicate_effect(counter):
    from shopman.shop.services import pos_sale_recovery

    original = pos_sale_recovery._save

    def lose_receipt(context, state):
        if state == "done":
            raise RuntimeError("receipt write lost")
        return original(context, state)

    with patch.object(pos_sale_recovery, "_save", side_effect=lose_receipt):
        with pytest.raises(PosCommittedSaleError):
            counter.close(client_request_id="lost-receipt", payment_method="pix")
    order = Order.objects.get()
    intent = PaymentIntent.objects.get(order_ref=order.ref)
    (entry,) = counter.sale_lines()
    with patch.object(payment_mock, "create_intent", side_effect=AssertionError("must not contact gateway")):
        recovered = counter.close(client_request_id="lost-receipt", payment_method="pix")
    assert recovered.order_ref == order.ref
    assert recovered.payment["intent_ref"] == intent.ref
    assert counter.sale_lines() == [entry]
    assert IdempotencyKey.objects.get(scope=SCOPE, key=order.ref).status == "done"


def test_two_connections_recover_local_failure_once(counter):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    from django.db import connection, connections

    if connection.vendor != "postgresql":
        pytest.skip("Independent PostgreSQL connections required")
    with patch.object(pos, "_record_sale", side_effect=RuntimeError("ledger disconnected")):
        with pytest.raises(PosCommittedSaleError):
            counter.close(client_request_id="parallel-recovery")
    barrier = Barrier(2)

    def resume(_):
        try:
            barrier.wait(timeout=10)
            return counter.close(client_request_id="parallel-recovery").order_ref
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        refs = list(pool.map(resume, range(2)))
    assert refs[0] == refs[1]
    assert Order.objects.count() == 1
    assert PaymentIntent.objects.filter(order_ref=refs[0]).count() == 1
    assert len(counter.sale_lines()) == 1


def test_cancelled_order_cannot_be_charged_by_recovery(counter):
    with patch.object(pos, "_record_sale", side_effect=RuntimeError("ledger disconnected")):
        with pytest.raises(PosCommittedSaleError):
            counter.close(client_request_id="cancelled-recovery")
    order = Order.objects.get()
    Order.objects.filter(pk=order.pk).update(status=Order.Status.CANCELLED)
    with pytest.raises(PosCommittedSaleError) as caught:
        counter.close(client_request_id="cancelled-recovery")
    assert_created_error(caught.value, order)
    assert caught.value.code == "sale_no_longer_settleable"
    assert not counter.sale_lines()
    assert not PaymentIntent.objects.filter(order_ref=order.ref).exists()


def test_retry_while_gateway_is_running_does_not_start_another_charge(counter):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    from django.db import connection, connections

    if connection.vendor != "postgresql":
        pytest.skip("Independent PostgreSQL connections required")
    entered, release = Event(), Event()
    original = payment_mock.create_intent

    def delayed(**kwargs):
        entered.set()
        assert release.wait(timeout=10)
        return original(**kwargs)

    def close():
        try:
            return counter.close(client_request_id="in-flight", payment_method="pix")
        finally:
            connections.close_all()

    with patch.object(payment_mock, "create_intent", side_effect=delayed) as create:
        with ThreadPoolExecutor(max_workers=1) as pool:
            first = pool.submit(close)
            try:
                assert entered.wait(timeout=10)
                with pytest.raises(PosCommittedSaleError) as replay:
                    counter.close(client_request_id="in-flight", payment_method="pix")
                assert replay.value.code == "sale_payment_outcome_unknown"
            finally:
                release.set()
            result = first.result(timeout=10)
        create.assert_called_once()
    assert Order.objects.count() == 1
    assert PaymentIntent.objects.filter(order_ref=result.order_ref).count() == 1
    assert len(counter.sale_lines()) == 1


def test_legacy_success_is_readable_but_missing_context_cannot_guess_drawer(counter):
    result = counter.close(client_request_id="legacy-success")
    IdempotencyKey.objects.filter(scope=SCOPE, key=result.order_ref).delete()
    assert counter.close(client_request_id="legacy-success").order_ref == result.order_ref
    with patch.object(pos, "_record_sale", side_effect=RuntimeError("ledger disconnected")):
        with pytest.raises(PosCommittedSaleError) as caught:
            counter.close(client_request_id="legacy-failure")
    IdempotencyKey.objects.filter(scope=SCOPE, key=caught.value.order_ref).delete()
    with pytest.raises(PosCommittedSaleError) as retry:
        counter.close(client_request_id="legacy-failure")
    assert retry.value.code == "sale_settlement_context_missing"
    assert retry.value.order_ref == caught.value.order_ref
    assert len(counter.sale_lines()) == 1


def test_local_receipt_failure_rolls_back_financial_effect_but_keeps_order(counter):
    from shopman.shop.services import pos_sale_recovery

    original = pos_sale_recovery._save

    def fail_receipt(context, state):
        if state == "done":
            raise RuntimeError("receipt unavailable")
        return original(context, state)

    with patch.object(pos_sale_recovery, "_save", side_effect=fail_receipt):
        with pytest.raises(PosCommittedSaleError) as caught:
            counter.close(client_request_id="local-receipt")
    order = Order.objects.get(ref=caught.value.order_ref)
    assert not counter.sale_lines()
    assert not PaymentIntent.objects.filter(order_ref=order.ref).exists()
    recovered = counter.close(client_request_id="local-receipt")
    assert recovered.order_ref == order.ref
    assert len(counter.sale_lines()) == 1
    assert PaymentIntent.objects.filter(order_ref=order.ref).count() == 1
