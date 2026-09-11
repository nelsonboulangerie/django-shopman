"""Use the canonical Payman returned-money semantics without inventing a status."""
import pytest
from shopman.orderman.models import Order
from shopman.payman.service import PaymentService

from shopman.shop.services import operator_orders, payment

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize("returned", [300, 1500])
def test_chargeback_funds_are_not_available_for_preparation_or_second_refund(returned):
    order = Order.objects.create(ref="CHARGEBACK-BALANCE", status="accepted", total_q=1500,
        data={"payment": {"method": "card"}})
    intent = PaymentService.create_intent(order.ref, 1500, "card")
    PaymentService.authorize(intent.ref)
    PaymentService.capture(intent.ref)
    order.data["payment"]["intent_ref"] = intent.ref
    order.save(update_fields=["data"])
    PaymentService.reconcile_gateway_status(intent.ref, gateway_status="captured", captured_q=1500, chargeback_q=returned)
    intent.refresh_from_db()
    assert intent.status == "captured"  # Existing Payman contract: amounts, no new state.
    assert PaymentService.chargeback_total(intent.ref) == returned
    assert payment.captured_balance_q(order) == 1500 - returned
    assert payment._payman_refundable_amount(intent.ref) == 1500 - returned
    for reads in (None, payment.read_payments_for([order])):
        assert not payment.has_sufficient_captured_payment(order, payment_reads=reads)
        assert operator_orders.advance_block(order, payment_reads=reads) == operator_orders.AdvanceBlock.PAYMENT_NOT_CAPTURED


def test_mixed_refund_and_chargeback_use_the_same_book_without_double_subtraction():
    intent = PaymentService.create_intent("MIXED-RETURNED", 2000, "pix")
    PaymentService.authorize(intent.ref)
    PaymentService.capture(intent.ref)
    order = Order.objects.create(ref="MIXED-RETURNED", status="accepted", total_q=1500,
        data={"payment": {"method": "pix", "intent_ref": intent.ref}})
    PaymentService.refund(intent.ref, amount_q=200)
    PaymentService.reconcile_gateway_status(intent.ref, gateway_status="captured", captured_q=2000, refunded_q=200, chargeback_q=300)
    assert payment.captured_balance_q(order) == 1500
    assert payment.has_sufficient_captured_payment(order)
    assert payment.has_sufficient_captured_payment(order, payment_reads=payment.read_payments_for([order]))
