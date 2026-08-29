"""A liquidação do cartão não pode depender de o cliente voltar à tela.

A rede contra webhook perdido nasceu num lugar só — a leitura do
acompanhamento, quando o cliente volta do Stripe. Enquanto for só ali, a
verdade do sistema fica pendurada no navegador do cliente: quem paga e fecha a
aba deixa o pedido ACCEPTED com o avanço barrado por "Aguardando pagamento…",
e do lado da loja não existe gesto capaz de destravar.

Aqui estão as duas portas que faltavam (o worker e o próprio Gestor) e o
silêncio que sobrava (captura recusada sem log, sem alerta, sem exceção).
"""

from __future__ import annotations

from io import StringIO
from unittest.mock import MagicMock, patch

from django.core.management import call_command
from django.test import TestCase, override_settings
from shopman.orderman.models import Order
from shopman.payman import PaymentService

from shopman.shop.models import Channel
from shopman.shop.tests.test_stripe_checkout_session import (
    PAYMENT_ADAPTERS_STRIPE_CARD,
    _commit_card_order,
)

STRIPE_MANUAL = {
    "secret_key": "sk_test_fake",
    "webhook_secret": "whsec_test_fake",
    "capture_method": "manual",
    "domain": "https://shop.example.com",
}


class FakeStripe:
    """SDK do Stripe suficiente para o ciclo do Checkout com captura manual.

    Dublê do SDK, não do nosso adapter: se o teste dublasse
    ``payment_stripe.capture`` ele deixaria de exercitar exatamente a linha que
    escreve a captura no Payman — e um verde assim não prova liquidação
    nenhuma.
    """

    def __init__(self, *, amount_q: int = 1000, capture_raises: bool = False):
        self.captured = False
        self.capture_raises = capture_raises
        self.amount_q = amount_q
        outer = self

        session = MagicMock()
        session.id = "cs_test_1"
        session.url = "https://checkout.stripe.com/c/pay/cs_test_1"
        session.payment_intent = "pi_test_1"
        session.status = "complete"
        self.session = session

        def _pi(status: str):
            pi = MagicMock()
            pi.id = "pi_test_1"
            pi.status = status
            pi.amount_received = outer.amount_q if status == "succeeded" else 0
            pi.latest_charge = "ch_1"
            return pi

        class _Session:
            @staticmethod
            def create(**kwargs):
                return outer.session

            @staticmethod
            def retrieve(sid):
                return outer.session

        class _Checkout:
            Session = _Session

        class _PaymentIntent:
            @staticmethod
            def retrieve(pid):
                return _pi("succeeded" if outer.captured else "requires_capture")

            @staticmethod
            def capture(pid, **kwargs):
                if outer.capture_raises:
                    raise RuntimeError("card_declined")
                outer.captured = True
                return _pi("succeeded")

        self.checkout = _Checkout
        self.PaymentIntent = _PaymentIntent


@override_settings(
    SHOPMAN_STRIPE=STRIPE_MANUAL,
    SHOPMAN_PAYMENT_ADAPTERS=PAYMENT_ADAPTERS_STRIPE_CARD,
    DEBUG=False,
)
class CardStuckAfterTheStoreAcceptedTests(TestCase):
    """O canal web aceita sozinho em 1 min — o aceite chega ANTES do pagamento."""

    def setUp(self) -> None:
        super().setUp()
        Channel.objects.get_or_create(
            ref="web",
            defaults={
                "name": "Loja online",
                "is_active": True,
                "config": {
                    "confirmation": {"mode": "auto_confirm", "timeout_minutes": 1},
                    "payment": {
                        "method": ["pix", "card"],
                        "timing": "post_commit",
                        "timeout_minutes": 10,
                    },
                },
            },
        )
        self.stripe = FakeStripe()

    def _order_paid_at_stripe_without_webhook(self) -> Order:
        """Pedido aceito, cliente pagou no Stripe, webhook nunca chegou."""
        with self.captureOnCommitCallbacks(execute=True):
            order = _commit_card_order()
        order.refresh_from_db()
        with self.captureOnCommitCallbacks(execute=True):
            order.transition_status(Order.Status.ACCEPTED, actor="confirmation.timeout")
        order.refresh_from_db()
        return order

    def test_the_worker_settles_a_card_nobody_came_back_for(self) -> None:
        from shopman.shop.adapters import payment_stripe
        from shopman.shop.services import operator_orders

        with patch.object(payment_stripe, "_get_stripe", return_value=self.stripe):
            order = self._order_paid_at_stripe_without_webhook()
            self.assertEqual(
                operator_orders.advance_block(order),
                operator_orders.AdvanceBlock.PAYMENT_NOT_CAPTURED,
            )

            # O cliente fechou a aba: ninguém vai reler o acompanhamento.
            with self.captureOnCommitCallbacks(execute=True):
                call_command("reconcile_payments", stdout=StringIO())

        order.refresh_from_db()
        self.assertEqual(operator_orders.advance_block(order), operator_orders.AdvanceBlock.NONE)

    def test_opening_the_order_in_the_gestor_asks_the_gateway(self) -> None:
        from django.contrib.auth import get_user_model
        from rest_framework.test import APIClient

        from shopman.shop.adapters import payment_stripe
        from shopman.shop.services import payment as payment_service

        user = get_user_model().objects.create_superuser("op", "op@example.com", "x")
        client = APIClient()
        client.force_authenticate(user=user)

        with patch.object(payment_stripe, "_get_stripe", return_value=self.stripe):
            order = self._order_paid_at_stripe_without_webhook()
            self.assertIsNot(payment_service.has_sufficient_captured_payment(order), True)

            with self.captureOnCommitCallbacks(execute=True):
                response = client.get(f"/api/v1/backstage/orders/{order.ref}/")

        self.assertEqual(response.status_code, 200)
        order.refresh_from_db()
        self.assertIs(payment_service.has_sufficient_captured_payment(order), True)

    def test_a_refused_capture_stops_being_silent(self) -> None:
        """Autorização de pé, dinheiro que não entra: alguém tem de ser avisado."""
        from shopman.backstage.models import OperatorAlert
        from shopman.shop.adapters import payment_stripe
        from shopman.shop.services import payment as payment_service

        self.stripe = FakeStripe(capture_raises=True)
        with patch.object(payment_stripe, "_get_stripe", return_value=self.stripe):
            order = self._order_paid_at_stripe_without_webhook()
            intent_ref = (order.data or {})["payment"]["intent_ref"]
            PaymentService.authorize(intent_ref, gateway_id="pi_test_1")

            with self.assertLogs("shopman.shop.services.payment", level="ERROR") as logs:
                payment_service.capture(order)

        self.assertTrue(any("payment.capture_failed" in line for line in logs.output))
        alert = OperatorAlert.objects.filter(type="payment_failed", order_ref=order.ref).first()
        self.assertIsNotNone(alert)
        self.assertIn("NÃO", alert.message)
