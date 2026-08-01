"""Tests for the surviving payment projection — the POS polling flags.

PAYMENT-TRACKING-MERGE apagou a tela de pagamento: o Pix/cartão do cliente
viraram um degrau do próprio acompanhamento (ver ``test_tracking_promise_cascade``
e ``test_projections_order_tracking``). O que sobra em ``shop.projections.
payment_status`` é o mínimo que o PDV consome para ver o Pix cair no balcão:
os flags terminais pago/cancelado/expirado.
"""
from __future__ import annotations

import pytest

from shopman.shop.projections.payment_status import PaymentStatusData, build_payment_status

pytestmark = pytest.mark.django_db


class TestPaymentStatusFlags:
    def test_pending_order_not_terminal(self, order_with_payment):
        proj = build_payment_status(order_with_payment)
        assert isinstance(proj, PaymentStatusData)
        assert proj.is_paid is False
        assert proj.is_cancelled is False
        assert proj.is_expired is False
        assert proj.is_terminal is False

    def test_paid_order_is_terminal(self, order_with_payment):
        from shopman.payman import PaymentService

        intent = PaymentService.create_intent(
            order_ref=order_with_payment.ref,
            amount_q=order_with_payment.total_q,
            method="pix",
        )
        order_with_payment.data["payment"]["intent_ref"] = intent.ref
        order_with_payment.save(update_fields=["data"])
        PaymentService.authorize(intent.ref, gateway_id="test-gw-001")
        PaymentService.capture(intent.ref)

        proj = build_payment_status(order_with_payment)
        assert proj.is_paid is True
        assert proj.is_terminal is True

    def test_cancelled_order_is_terminal(self, order_with_payment):
        order_with_payment.status = "cancelled"
        order_with_payment.save(update_fields=["status"])

        proj = build_payment_status(order_with_payment)
        assert proj.is_cancelled is True
        assert proj.is_terminal is True

    def test_expired_pix_is_terminal(self, order_with_payment):
        from django.utils import timezone

        order_with_payment.data["payment"]["expires_at"] = (
            timezone.now().replace(microsecond=0) - timezone.timedelta(minutes=5)
        ).isoformat()
        order_with_payment.save(update_fields=["data"])

        proj = build_payment_status(order_with_payment)
        assert proj.is_expired is True
        assert proj.is_terminal is True

    def test_is_immutable(self, order_with_payment):
        from dataclasses import FrozenInstanceError

        proj = build_payment_status(order_with_payment)
        with pytest.raises(FrozenInstanceError):
            proj.is_paid = True  # type: ignore[misc]
