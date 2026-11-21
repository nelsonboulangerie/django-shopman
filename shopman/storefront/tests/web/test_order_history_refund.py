"""Lista de pedidos da Conta: o cancelado com dinheiro que volta diz o dinheiro (#2992).

Antes, a linha dizia "Cancelado · R$ 25,00" para o pedido cujo Pix já tinha voltado:
a cliente lia o cancelamento e o total, e ficava sem saber do dinheiro. Agora a linha
diz "Devolvido · <o que voltou>" ou, enquanto o estorno não fecha, "Devolução em
andamento · <o que falta voltar>". O acompanhamento do pedido não muda.
"""
from __future__ import annotations

import pytest
from shopman.orderman.models import Order
from shopman.payman import PaymentService

from shopman.storefront.presentation.account import order_history_for_customer
from shopman.storefront.presentation.order_history import build_order_history

pytestmark = pytest.mark.django_db


@pytest.fixture
def order_with_payment(channel, customer):
    """Pedido Pix de R$ 25,00 da cliente (ligado pelo ``customer_ref``, como a loja liga)."""
    return Order.objects.create(
        ref="ORD-REFUND-001",
        channel_ref=channel.ref,
        status="new",
        total_q=2500,
        handle_type="phone",
        handle_ref=customer.phone,
        data={"customer_ref": customer.ref, "payment": {"method": "pix", "amount_q": 2500}},
    )


def _cancel_with_captured_pix(order, *, amount_q=None):
    intent = PaymentService.create_intent(
        order_ref=order.ref,
        amount_q=amount_q if amount_q is not None else order.total_q,
        method="pix",
    )
    PaymentService.authorize(intent.ref)
    PaymentService.capture(intent.ref)
    data = {**(order.data or {}), "payment": {"method": "pix", "intent_ref": intent.ref}}
    Order.objects.filter(pk=order.pk).update(status="cancelled", data=data)
    order.refresh_from_db()
    return intent


def _row(customer):
    (summary,) = build_order_history(customer).orders
    return summary


class TestRefundedCancelledOrder:
    def test_refunded_pix_says_devolvido_with_the_amount_back(self, customer, order_with_payment):
        intent = _cancel_with_captured_pix(order_with_payment)
        PaymentService.refund(intent.ref, reason="cancelled")

        row = _row(customer)

        assert row.status_label == "Devolvido"
        assert row.total_display == "R$ 25,00"
        assert row.status == "cancelled"

    def test_refund_not_closed_says_em_andamento(self, customer, order_with_payment):
        _cancel_with_captured_pix(order_with_payment)

        row = _row(customer)

        assert row.status_label == "Devolução em andamento"
        assert row.total_display == "R$ 25,00"

    def test_partial_refund_shows_what_is_still_coming_back(self, customer, order_with_payment):
        intent = _cancel_with_captured_pix(order_with_payment)
        PaymentService.refund(intent.ref, amount_q=1000, reason="cancelled")

        row = _row(customer)

        assert row.status_label == "Devolução em andamento"
        assert row.total_display == "R$ 15,00"

    def test_api_row_carries_label_amount_and_tone(self, customer, order_with_payment):
        intent = _cancel_with_captured_pix(order_with_payment)
        PaymentService.refund(intent.ref, reason="cancelled")

        (row,) = order_history_for_customer(customer_ref=customer.ref, phone=customer.phone)

        assert row["status_label"] == "Devolvido"
        assert row["total_display"] == "R$ 25,00"
        assert row["status_tone"] == "neutral"
        assert row["is_active"] is False

    def test_refund_in_progress_tone_is_warning(self, customer, order_with_payment):
        _cancel_with_captured_pix(order_with_payment)

        (row,) = order_history_for_customer(customer_ref=customer.ref, phone=customer.phone)

        assert row["status_tone"] == "warning"


class TestCancelledWithoutMoneyBack:
    def test_nothing_charged_stays_cancelado_with_the_total(self, customer, order_with_payment):
        Order.objects.filter(pk=order_with_payment.pk).update(status="cancelled")

        row = _row(customer)

        assert row.status_label != "Devolvido"
        assert row.status_label != "Devolução em andamento"
        assert row.total_display == "R$ 25,00"

    def test_active_order_is_untouched(self, customer, order_with_payment):
        row = _row(customer)

        assert row.status_label not in {"Devolvido", "Devolução em andamento"}
