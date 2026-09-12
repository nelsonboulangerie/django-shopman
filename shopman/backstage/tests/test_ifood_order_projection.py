"""iFood facts stay visible without marking unpaid imports as paid online."""

from types import SimpleNamespace

import pytest

from shopman.backstage.projections import ifood, order_queue


def _order(*, payments=None, cancellation_request=None, status="accepted", channel="ifood"):
    return SimpleNamespace(
        channel_ref=channel, status=status, total_q=3000,
        data={
            "payment": {"method": "external", "gateway": "ifood", "status": "paid"},
            "ifood": {"payments": payments or {}},
            "ifood_cancellation_request": cancellation_request or {},
        },
    )


@pytest.mark.parametrize("cancellation_request,fragment", [
    ({"state": "queued"}, "ainda não foi cancelado"),
    ({"state": "sent"}, "Aguardando confirmação"),
    ({"state": "error", "retryable": True}, "confirmação continua pendente"),
    ({"state": "error", "retryable": False}, "pedido continua ativo"),
])
def test_cancellation_request_is_not_presented_as_effective_cancellation(cancellation_request, fragment):
    assert fragment in ifood.cancellation_notice(_order(cancellation_request=cancellation_request))


@pytest.mark.parametrize("status", ["cancelled", "completed", "returned"])
def test_terminal_orders_hide_stale_cancellation_requests(status):
    assert ifood.cancellation_notice(_order(status=status, cancellation_request={"state": "sent"})) == ""


@pytest.mark.parametrize("cancellation_request", [{}, {"state": "confirmed"}, {"state": "future-state"}])
def test_no_active_request_has_no_notice(cancellation_request):
    assert ifood.cancellation_notice(_order(cancellation_request=cancellation_request)) == ""


def test_other_channels_never_inherit_ifood_notice_or_payment_summary():
    order = _order(channel="web", payments={"prepaid_q": 3000}, cancellation_request={"state": "sent"})
    assert ifood.cancellation_notice(order) == ""
    assert ifood.payment_summary(order) == ()


def test_missing_payment_does_not_claim_online_payment():
    assert ifood.payment_summary(_order()) == ("iFood: pagamento não informado.",)


def test_online_payment_preserves_card_brand():
    summary = ifood.payment_summary(_order(payments={
        "prepaid_q": 3000, "pending_q": 0,
        "methods": [{"method": "CREDIT", "value_q": 3000, "prepaid": True, "brand": "VISA"}],
    }))
    assert summary == ("Pago online no iFood: R$ 30,00", "Crédito VISA: R$ 30,00 (online)")


def test_offline_credit_is_pending_and_keeps_its_brand():
    summary = ifood.payment_summary(_order(payments={
        "prepaid_q": 0, "pending_q": 3000,
        "methods": [{"method": "CREDIT", "value_q": 3000, "prepaid": False, "brand": "ELO"}],
    }))
    assert summary == ("Pagamento pendente no iFood: R$ 30,00", "Crédito ELO: R$ 30,00 (pendente)")


def test_mixed_payment_cash_change_uses_cash_part_not_order_total():
    summary = ifood.payment_summary(_order(payments={
        "prepaid_q": 1000, "pending_q": 2000,
        "methods": [
            {"method": "CREDIT", "value_q": 1000, "prepaid": True, "brand": "VISA"},
            {"method": "CASH", "value_q": 2000, "prepaid": False, "change_for_q": 5000},
        ],
    }))
    assert summary[:2] == ("Pago online no iFood: R$ 10,00", "Pagamento pendente no iFood: R$ 20,00")
    assert summary[-1] == "Dinheiro: R$ 20,00 (pendente); troco para R$ 50,00, troco R$ 30,00"


def test_invalid_cash_change_does_not_invent_negative_change():
    summary = ifood.payment_summary(_order(payments={
        "pending_q": 3000,
        "methods": [{"method": "CASH", "value_q": 3000, "prepaid": False, "change_for_q": 1000}],
    }))
    assert "troco para R$ 10,00" in summary[-1]
    assert "troco R$ -" not in summary[-1]


def test_prepaid_cash_does_not_prompt_second_collection_or_change():
    summary = ifood.payment_summary(_order(payments={
        "prepaid_q": 3000,
        "methods": [{"method": "CASH", "value_q": 3000, "prepaid": True, "change_for_q": 5000}],
    }))
    assert not any("troco" in line or "pendente" in line for line in summary)


@pytest.mark.parametrize("payments,expected,tone", [
    ({"prepaid_q": 3000, "pending_q": 0}, "paid", "success"),
    ({"prepaid_q": 0, "pending_q": 3000}, "pending", "neutral"),
    ({"prepaid_q": 1000, "pending_q": 2000}, "pending", "neutral"),
    ({}, "unknown", "warning"),
])
@pytest.mark.parametrize("builder", [order_queue.build_order_card, order_queue.build_operator_order])
@pytest.mark.django_db
def test_builders_override_legacy_paid_with_ifood_evidence_without_local_collection(payments, expected, tone, builder):
    from shopman.orderman.models import Order

    from shopman.shop.models import Channel

    Channel.objects.get_or_create(ref="ifood", defaults={
        "name": "iFood", "config": {"payment": {"method": "external", "timing": "external"}},
    })
    data = _order(payments=payments, cancellation_request={"state": "sent"}).data
    data.update({"fulfillment_type": "delivery", "availability_decision": {"approved": True}})
    order = Order.objects.create(
        ref="IFOOD-PROJECTION", channel_ref="ifood", status="accepted", total_q=3000,
        external_ref="ifood-test", data=data,
    )
    projected = builder(order)
    assert projected.payment_status == expected
    if hasattr(projected, "payment_tone"):
        assert projected.payment_tone == tone
        assert projected.payment_pending is False  # collection must not gate preparation
    if expected != "paid":
        assert "pago online" not in projected.payment_method_label.lower()
    if expected == "paid":
        assert projected.payment_status_label != "paid"
    assert projected.ifood_payment_summary == ifood.payment_summary(order)
    assert projected.ifood_cancellation_notice == ifood.cancellation_notice(order)
    assert projected.can_settle_delivery_cash is False
    assert projected.can_advance is False
    if hasattr(projected, "can_cancel"):
        assert projected.can_cancel is False
        assert "iFood" in projected.cancel_block_label
    order.refresh_from_db()
    assert order.data["payment"]["status"] == "paid"  # projection is read-only
    assert "intent_ref" not in order.data["payment"]


@pytest.mark.django_db
def test_batched_board_retains_ifood_payment_evidence():
    from shopman.orderman.models import Order

    from shopman.shop.models import Channel

    Channel.objects.get_or_create(ref="ifood", defaults={"name": "iFood"})
    Order.objects.create(
        ref="IFOOD-BOARD", channel_ref="ifood", status="new", total_q=3000,
        data=_order(payments={"pending_q": 3000, "prepaid_q": 0}, cancellation_request={"state": "queued"}).data,
    )
    board = order_queue.build_two_zone_queue()
    card = next(card for card in board.intake if card.ref == "IFOOD-BOARD")
    assert card.payment_status == "pending"
    assert card.payment_tone == "neutral"
    assert "pago online" not in card.payment_method_label.lower()
    assert card.ifood_payment_summary == ("Pagamento pendente no iFood: R$ 30,00",)
    assert "ainda não foi cancelado" in card.ifood_cancellation_notice
