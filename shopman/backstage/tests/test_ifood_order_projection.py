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
    assert ifood.payment_headline(_order()) == "Pagamento não informado pelo iFood"
    assert ifood.payment_summary(_order()) == ()


def test_online_payment_preserves_card_brand():
    order = _order(payments={
        "prepaid_q": 3000, "pending_q": 0,
        "methods": [{"method": "CREDIT", "value_q": 3000, "prepaid": True, "brand": "VISA"}],
    })
    # Pago online é uma frase só: bandeira e banco não mudam o despacho (3417, 12/11),
    # e nada se repete abaixo dela (dono, 14/11).
    assert ifood.payment_headline(order) == "Pago online no iFood: nada a cobrar"
    assert ifood.payment_summary(order) == ()


def test_offline_credit_is_pending_and_keeps_its_brand():
    order = _order(payments={
        "prepaid_q": 0, "pending_q": 3000,
        "methods": [{"method": "CREDIT", "value_q": 3000, "prepaid": False, "brand": "ELO"}],
    })
    assert ifood.payment_headline(order) == "Cobrar na entrega: R$ 30,00 em crédito ELO"
    assert ifood.payment_summary(order) == ()


def test_mixed_payment_cash_change_uses_cash_part_not_order_total():
    order = _order(payments={
        "prepaid_q": 1000, "pending_q": 2000,
        "methods": [
            {"method": "CREDIT", "value_q": 1000, "prepaid": True, "brand": "VISA"},
            {"method": "CASH", "value_q": 2000, "prepaid": False, "change_for_q": 5000},
        ],
    })
    assert ifood.payment_headline(order) == (
        "Cobrar na entrega: R$ 20,00 em dinheiro; troco para R$ 50,00 (levar R$ 30,00)"
    )
    assert ifood.payment_summary(order) == ("Já pago online no iFood: R$ 10,00",)


def test_split_collection_lists_each_form_once():
    order = _order(payments={
        "prepaid_q": 0, "pending_q": 3000,
        "methods": [
            {"method": "DEBIT", "value_q": 1000, "prepaid": False, "brand": "VISA"},
            {"method": "CASH", "value_q": 2000, "prepaid": False},
        ],
    })
    assert ifood.payment_headline(order) == "Cobrar na entrega: R$ 30,00"
    assert ifood.payment_summary(order) == ("Débito VISA: R$ 10,00", "Dinheiro: R$ 20,00")


def test_invalid_cash_change_does_not_invent_negative_change():
    headline = ifood.payment_headline(_order(payments={
        "pending_q": 3000,
        "methods": [{"method": "CASH", "value_q": 3000, "prepaid": False, "change_for_q": 1000}],
    }))
    assert "troco para R$ 10,00" in headline
    assert "levar" not in headline


def test_prepaid_cash_does_not_prompt_second_collection_or_change():
    order = _order(payments={
        "prepaid_q": 3000,
        "methods": [{"method": "CASH", "value_q": 3000, "prepaid": True, "change_for_q": 5000}],
    })
    assert ifood.payment_headline(order) == "Pago online no iFood: nada a cobrar"
    assert ifood.payment_summary(order) == ()


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
    # A evidência textual por bandeira é do DETALHE; no card o que não pode mentir
    # é o pill, checado acima (status, tom e rótulo). O aviso de cancelamento fica
    # nos dois: é estado do pedido, não evidência financeira.
    if hasattr(projected, "ifood_payment_summary"):
        assert projected.ifood_payment_summary == ifood.payment_summary(order)
        # No detalhe a linha do pagamento é a frase inteira, sem "· status" repetido.
        assert projected.payment_method_label == ifood.payment_headline(order)
        assert projected.payment_status_label == ""
    else:
        assert projected.ifood_pickup_code == ifood.pickup_code(order)
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
    assert "ainda não foi cancelado" in card.ifood_cancellation_notice
    # O card não carrega mais o desdobramento: quem precisa dele abre o detalhe, e
    # é lá que a evidência tem de continuar inteira.
    assert not hasattr(card, "ifood_payment_summary")
    detail = order_queue.build_operator_order(Order.objects.get(ref="IFOOD-BOARD"))
    assert detail.payment_method_label == "Cobrar na entrega: R$ 30,00"
    assert detail.ifood_payment_summary == ()


# ── P2-29: a hora da retirada (``takeout.takeoutDateTime``) ──────────────────


def _takeout(takeout_at, *, timing="IMMEDIATE", fulfillment="pickup"):
    return SimpleNamespace(
        channel_ref="ifood", status="accepted", total_q=3000,
        data={"fulfillment_type": fulfillment, "ifood": {"order_timing": timing, "takeout_at": takeout_at}},
    )


def test_immediate_takeout_shows_when_the_customer_comes():
    from datetime import timedelta

    from django.utils import timezone

    today = timezone.localtime().replace(hour=19, minute=40, second=0, microsecond=0)
    assert ifood.schedule_label(_takeout(today.isoformat())) == "Retirada às 19:40"
    other_day = today + timedelta(days=1)
    assert ifood.schedule_label(_takeout(other_day.isoformat())) == f"Retirada {other_day:%d/%m} às 19:40"
    assert f"Retirada prevista: {today:%d/%m/%Y} às 19:40" in ifood.operation_summary(_takeout(today.isoformat()))


def test_takeout_time_is_silent_when_scheduled_delivery_or_without_timezone():
    from django.utils import timezone

    aware = timezone.now().isoformat()
    assert ifood.schedule_label(_takeout(aware, fulfillment="delivery")) == ""
    assert ifood.schedule_label(_takeout("2026-10-13T22:40:00")) == ""
    assert ifood.schedule_label(_takeout("")) == ""
    assert ifood.schedule_label(_takeout(aware, timing="SCHEDULED")) == "Agendado"
    assert not any("Retirada prevista" in line for line in ifood.operation_summary(_takeout(aware, timing="SCHEDULED")))


@pytest.mark.django_db
def test_courier_line_says_ifood_picks_the_courier_until_it_does():
    order = _order(payments={"prepaid_q": 3000})
    order.ref = "IFOOD-COURIER-LINE"
    order.data["fulfillment_type"] = "delivery"
    order.data["ifood"]["delivered_by"] = "IFOOD"
    assert "Entregador do iFood: o iFood designa perto da hora de sair" in ifood.operation_summary(order)
    # Designado, quem diz o nome e o andamento é o selo do cabeçalho: a linha sai.
    order.data["ifood"]["logistics"] = {"ASSIGN_DRIVER": {"metadata": {"workerName": "Marcos"}}}
    assert ifood.logistics_label(order) == "Entregador do iFood designado: Marcos"
    assert not any(line.startswith("Entregador do iFood") for line in ifood.operation_summary(order))
