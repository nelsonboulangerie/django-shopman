"""Cartão autorizado cuja cobrança no aceite falhou: um estado só, nos dois lados.

Beta 06/11: a captura no aceite foi recusada (autorização vencida ou recusada
pelo emissor). O cliente seguia lendo "Cartão autorizado. Pedido aceito"; o
Gestor dizia "Cartão · Autorizado" e "Aguardando pagamento · link gerado" ao
mesmo tempo, e o alerta só existia na lista de alertas, fora da ficha do
pedido. Cancelado o pedido, o cliente lia "Não recebemos a confirmação do
pagamento a tempo", que joga a culpa nele e cala a reserva no cartão.

Stripe dublado no SDK (``FakeStripe``): a captura levanta como levantaria uma
autorização vencida, e a anulação no cancelamento passa.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings
from shopman.orderman.models import Order
from shopman.payman import PaymentService

from shopman.shop.models import Channel
from shopman.shop.tests.test_card_settles_without_the_customer import STRIPE_MANUAL, FakeStripe
from shopman.shop.tests.test_stripe_checkout_session import (
    PAYMENT_ADAPTERS_STRIPE_CARD,
    _commit_card_order,
)


def _cancel_pi(pid, **kwargs):
    pi = MagicMock()
    pi.id = pid
    pi.status = "canceled"
    return pi


@override_settings(
    SHOPMAN_STRIPE=STRIPE_MANUAL,
    SHOPMAN_PAYMENT_ADAPTERS=PAYMENT_ADAPTERS_STRIPE_CARD,
    DEBUG=False,
)
class CardCaptureFailedTests(TestCase):
    def setUp(self) -> None:
        super().setUp()
        Channel.objects.get_or_create(
            ref="web",
            defaults={
                "name": "Loja online",
                "is_active": True,
                "config": {
                    "confirmation": {"mode": "manual"},
                    "payment": {"method": ["pix", "card"], "timing": "at_commit", "timeout_minutes": 10},
                },
            },
        )
        self.stripe = FakeStripe(capture_raises=True)
        self.stripe.PaymentIntent.cancel = staticmethod(_cancel_pi)
        from shopman.shop.adapters import payment_stripe

        patcher = patch.object(payment_stripe, "_get_stripe", return_value=self.stripe)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _accepted_with_failed_capture(self) -> Order:
        with self.captureOnCommitCallbacks(execute=True):
            order = _commit_card_order()
        order.refresh_from_db()
        PaymentService.authorize(order.data["payment"]["intent_ref"], gateway_id="pi_test_1")
        with self.assertLogs("shopman.shop.services.payment", level="ERROR"):
            with self.captureOnCommitCallbacks(execute=True):
                order.transition_status(Order.Status.ACCEPTED, actor="operator")
        order.refresh_from_db()
        return order

    def test_the_failure_is_recorded_on_the_order(self) -> None:
        from shopman.shop.services import payment as payment_service

        order = self._accepted_with_failed_capture()
        failure = payment_service.capture_failure(order)
        self.assertIsNotNone(failure)
        self.assertEqual(failure["intent_ref"], order.data["payment"]["intent_ref"])
        self.assertTrue(order.events.filter(type="payment.capture_failed").exists())

    def test_the_customer_reads_that_the_charge_did_not_go_through(self) -> None:
        from shopman.storefront.presentation.order_tracking import build_order_tracking

        order = self._accepted_with_failed_capture()
        tracking = build_order_tracking(order)
        self.assertEqual(tracking.promise.state, "payment_capture_failed")
        self.assertEqual(tracking.promise.title, "Não conseguimos cobrar o cartão")
        self.assertIn("nada foi cobrado", tracking.promise.message)
        self.assertNotIn("autorizado", tracking.promise.message.lower())
        self.assertEqual(tracking.payment_status_label, "Cobrança não concluída")

    def test_the_gestor_shows_one_state_with_the_alert_in_the_order(self) -> None:
        from django.contrib.auth import get_user_model

        from shopman.backstage.projections.order_queue import (
            CARD_CAPTURE_FAILED_LABEL,
            build_operator_order,
            build_order_card,
        )

        order = self._accepted_with_failed_capture()
        user = get_user_model().objects.create_superuser("gestor", "g@example.com", "x")
        for projection in (build_operator_order(order, user=user), build_order_card(order, user=user)):
            # A pílula e o bloqueio dizem a mesma coisa; nada de "Autorizado" ao
            # lado de "Aguardando pagamento · link gerado".
            self.assertEqual(projection.payment_status_label, CARD_CAPTURE_FAILED_LABEL)
            self.assertEqual(projection.advance_block_label, CARD_CAPTURE_FAILED_LABEL)
            self.assertNotIn("link gerado", projection.advance_block_reason)
            self.assertIn("nada foi cobrado", projection.advance_block_reason)
            # O aviso da ficha traz o próximo passo pronto: cancelar com o motivo marcado.
            self.assertTrue(projection.payment_lapsed)
        card = build_order_card(order, user=user)
        self.assertEqual(card.payment_tone, "danger")

    def test_a_later_successful_capture_clears_the_failure(self) -> None:
        from shopman.shop.services import payment as payment_service

        order = self._accepted_with_failed_capture()
        self.stripe.capture_raises = False
        payment_service.capture(order)
        order.refresh_from_db()
        self.assertIsNone(payment_service.capture_failure(order))
        self.assertNotIn(payment_service.CAPTURE_FAILURE_KEY, order.data["payment"])

    def test_cancelling_says_nothing_was_charged_and_the_hold_was_released(self) -> None:
        from shopman.shop.services import cancel_reasons, operator_orders
        from shopman.storefront.presentation.order_tracking import build_order_tracking

        order = self._accepted_with_failed_capture()
        with self.captureOnCommitCallbacks(execute=True):
            self.assertTrue(
                operator_orders.cancel_order(
                    order, reason="operator", actor="gestor", reason_key="payment_not_confirmed",
                )
            )
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.CANCELLED)

        # O texto do aviso (que não tem bloco de dinheiro) diz o que houve com o dinheiro.
        text = cancel_reasons.customer_text(order.data)
        self.assertNotIn("a tempo", text)
        self.assertIn("Nada foi cobrado", text)
        self.assertIn("reserva", text)

        tracking = build_order_tracking(order)
        self.assertEqual(tracking.cancellation_note, text)
        # A mesma frase não se repete no bloco do dinheiro, logo abaixo.
        self.assertEqual(tracking.cancellation_money_line, "")
