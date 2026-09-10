"""PIX confirmation parity for the local mock payment gateway."""

from __future__ import annotations

import base64
import json
from unittest.mock import patch

from django.test import TestCase
from shopman.orderman.exceptions import DirectiveTerminalError
from shopman.orderman.models import Directive, Order
from shopman.payman import PaymentService
from shopman.payman.models import PaymentIntent

from shopman.shop.adapters import payment_mock
from shopman.shop.handlers.mock_pix import MOCK_PIX_CONFIRM, MockPixConfirmHandler


class MockPixConfirmationTests(TestCase):
    def test_mock_pix_intent_does_not_auto_schedule_confirmation_by_default(self) -> None:
        order = Order.objects.create(
            ref="PIX-MOCK-MANUAL",
            channel_ref="web",
            status="accepted",
            total_q=1500,
            data={"payment": {"method": "pix"}},
        )

        intent = payment_mock.create_intent(
            order_ref=order.ref,
            amount_q=order.total_q,
            method="pix",
        )

        # Intent recém-criado no simulador é `pending`: quem autoriza é gateway.
        self.assertEqual(PaymentService.get(intent.intent_ref).status, "pending")
        self.assertFalse(
            Directive.objects.filter(
                topic=MOCK_PIX_CONFIRM,
                payload__order_ref=order.ref,
            ).exists()
        )

    def test_scheduled_mock_pix_does_not_capture_before_available_at(self) -> None:
        order = Order.objects.create(
            ref="PIX-MOCK-SCHEDULED",
            channel_ref="web",
            status="new",
            total_q=1500,
            data={"payment": {"method": "pix"}},
        )

        with self.captureOnCommitCallbacks(execute=True):
            intent = payment_mock.create_intent(
                order_ref=order.ref,
                amount_q=order.total_q,
                method="pix",
                mock_pix_auto_confirm=True,
                mock_pix_confirm_delay_seconds=30,
            )

        directive = Directive.objects.filter(topic=MOCK_PIX_CONFIRM).latest("id")

        # Agendado ≠ pago: a cobrança fica `pending` até a directive rodar.
        self.assertEqual(PaymentService.get(intent.intent_ref).status, "pending")
        self.assertEqual(directive.status, "queued")
        self.assertEqual(directive.attempts, 0)

    def test_mock_pix_intent_returns_real_png_qr_image(self) -> None:
        order = Order.objects.create(
            ref="PIX-MOCK-QR",
            channel_ref="web",
            status="accepted",
            total_q=1500,
            data={"payment": {"method": "pix"}},
        )

        intent = payment_mock.create_intent(
            order_ref=order.ref,
            amount_q=order.total_q,
            method="pix",
            mock_pix_auto_confirm=True,
            mock_pix_confirm_delay_seconds=30,
        )

        qr_image = intent.metadata["imagemQrcode"]
        self.assertTrue(qr_image.startswith("data:image/png;base64,"))
        png_bytes = base64.b64decode(qr_image.split(",", 1)[1])
        self.assertEqual(png_bytes[:8], b"\x89PNG\r\n\x1a\n")
        self.assertNotIn("svg+xml", qr_image)

        payload = json.loads(intent.client_secret)
        self.assertEqual(payload["qrcode"], payload["brcode"])
        self.assertEqual(payload["imagemQrcode"], qr_image)

    def test_mock_refuses_card_outright(self) -> None:
        """O simulador não atende cartão — e recusa alto, sem criar intent.

        ⚠️ Este teste chamava-se `test_mock_card_intent_does_not_inherit_pix_
        deadline_or_qr` e afirmava `persisted.status == "authorized"`. Era a
        asserção que blindava o P0: um teste que AFIRMA que o cartão do
        simulador nasce autorizado jamais poderia pegar o pedido dado por pago
        sem passar pelo Stripe. Hoje o ramo de cartão não existe mais aqui; o
        cartão de teste do Stripe exercita o caminho real.
        """
        order = Order.objects.create(
            ref="CARD-MOCK-NO-PIX",
            channel_ref="web",
            status="new",
            total_q=1500,
            data={"payment": {"method": "card"}},
        )

        with self.assertRaises(payment_mock.MockCardNotSupported):
            payment_mock.create_intent(
                order_ref=order.ref,
                amount_q=order.total_q,
                method="card",
            )

        # Recusa antes de escrever: nenhum intent órfão fica para trás.
        self.assertEqual(PaymentIntent.objects.filter(order_ref=order.ref).count(), 0)

    def test_mock_pix_directive_captures_mock_gateway_intent(self) -> None:
        from shopman.backstage.models import OperatorAlert

        order = Order.objects.create(
            ref="PIX-MOCK-001",
            channel_ref="web",
            status="new",
            total_q=1500,
            data={"payment": {"method": "pix"}},
        )
        alert = OperatorAlert.objects.create(
            type="payment_failed",
            severity="error",
            order_ref=order.ref,
            message=f"Falha ao gerar pagamento PIX do pedido {order.ref}.",
        )
        intent = payment_mock.create_intent(
            order_ref=order.ref,
            amount_q=order.total_q,
            method="pix",
            mock_pix_auto_confirm=True,
            mock_pix_confirm_delay_seconds=0,
        )
        stale_intent = PaymentService.create_intent(
            order_ref=order.ref,
            amount_q=order.total_q,
            method="pix",
        )
        order.data["payment"]["intent_ref"] = intent.intent_ref
        order.save(update_fields=["data", "updated_at"])

        directive = Directive.objects.filter(topic=MOCK_PIX_CONFIRM).latest("id")

        with patch("shopman.shop.lifecycle.dispatch") as mock_dispatch:
            MockPixConfirmHandler().handle(message=directive, ctx={})

        self.assertEqual(PaymentService.get(intent.intent_ref).status, "captured")
        self.assertEqual(PaymentService.get(stale_intent.ref).status, "cancelled")
        order.refresh_from_db()
        self.assertEqual(order.data["payment"]["e2e_id"], directive.payload["e2e_id"])
        alert.refresh_from_db()
        self.assertTrue(alert.acknowledged)
        mock_dispatch.assert_called_once_with(order, "on_paid")

    def test_legacy_mock_pix_directive_without_opt_in_does_not_capture(self) -> None:
        order = Order.objects.create(
            ref="PIX-MOCK-LEGACY",
            channel_ref="web",
            status="accepted",
            total_q=1500,
            data={"payment": {"method": "pix"}},
        )
        intent = payment_mock.create_intent(
            order_ref=order.ref,
            amount_q=order.total_q,
            method="pix",
        )
        order.data["payment"]["intent_ref"] = intent.intent_ref
        order.save(update_fields=["data", "updated_at"])
        directive = Directive.objects.create(
            topic=MOCK_PIX_CONFIRM,
            payload={
                "order_ref": order.ref,
                "txid": intent.gateway_id,
                "e2e_id": "E2ELEGACY",
                "valor": "15.00",
            },
        )

        with self.assertRaises(DirectiveTerminalError):
            MockPixConfirmHandler().handle(message=directive, ctx={})

        # O que este teste afirma é "não capturou". O estado parado é `pending`:
        # o simulador não autoriza nada por conta própria — autorizar é fala de
        # gateway. Antes dizia `authorized` só porque o mock se autoautorizava
        # no `create_intent`, que é justamente o bug de dar pedido por pago sem
        # cobrar. Ver `test_payment_never_authorized_without_gateway.py`.
        self.assertEqual(PaymentService.get(intent.intent_ref).status, "pending")


class MockPixManualVersusAutoConfirmTests(TestCase):
    """O botão "Simular pagamento" e o auto-confirm se contradizem — o botão vence.

    Com as duas envs ligadas, o timer de segundos sempre ganhava a corrida do
    dedo: o Pix se confirmava sozinho e o botão manual nem chegava a aparecer.
    A decisão mora em `_adapter_config` (services/payment.py): com o botão
    exposto, o auto-confirm não é injetado no adapter mock.
    """

    def _order(self, ref: str) -> Order:
        return Order.objects.create(
            ref=ref,
            channel_ref="web",
            status="accepted",
            total_q=1500,
            data={"payment": {"method": "pix"}},
        )

    def test_botao_manual_exposto_desliga_o_auto_confirm(self) -> None:
        from django.test import override_settings

        from shopman.shop.services import payment as payment_service

        order = self._order("PIX-MOCK-BUTTON-WINS")

        with override_settings(
            SHOPMAN_EXPOSE_MOCK_CAPTURE=True,
            SHOPMAN_MOCK_PIX_AUTO_CONFIRM=True,
            SHOPMAN_MOCK_PIX_CONFIRM_DELAY_SECONDS=8,
        ):
            config = payment_service._adapter_config(order, method="pix")
            self.assertNotIn("mock_pix_auto_confirm", config)

            payment_mock.create_intent(
                order_ref=order.ref,
                amount_q=order.total_q,
                method="pix",
                **config,
            )

        # Nenhum despertador agendado: quem confirma é a pessoa, no botão.
        self.assertFalse(
            Directive.objects.filter(
                topic=MOCK_PIX_CONFIRM,
                payload__order_ref=order.ref,
            ).exists()
        )

    def test_auto_confirm_sozinho_continua_agendando(self) -> None:
        """Compat: ambiente sem gente clicando (só auto-confirm) segue como era."""
        from django.test import override_settings

        from shopman.shop.services import payment as payment_service

        order = self._order("PIX-MOCK-AUTO-ONLY")

        with override_settings(
            SHOPMAN_EXPOSE_MOCK_CAPTURE=False,
            SHOPMAN_MOCK_PIX_AUTO_CONFIRM=True,
            SHOPMAN_MOCK_PIX_CONFIRM_DELAY_SECONDS=8,
        ):
            config = payment_service._adapter_config(order, method="pix")
            self.assertIs(config["mock_pix_auto_confirm"], True)
            self.assertEqual(config["mock_pix_confirm_delay_seconds"], 8)

            payment_mock.create_intent(
                order_ref=order.ref,
                amount_q=order.total_q,
                method="pix",
                **config,
            )

        self.assertTrue(
            Directive.objects.filter(
                topic=MOCK_PIX_CONFIRM,
                payload__order_ref=order.ref,
            ).exists()
        )

    def test_check_avisa_quando_as_duas_envs_estao_ligadas(self) -> None:
        from django.test import override_settings

        from shopman.shop import checks as shop_checks

        with override_settings(
            SHOPMAN_EXPOSE_MOCK_CAPTURE=True,
            SHOPMAN_MOCK_PIX_AUTO_CONFIRM=True,
        ):
            messages = shop_checks.check_mock_pix_confirm_conflict(None)
        self.assertEqual([m.id for m in messages], ["SHOPMAN_W018"])

        with override_settings(
            SHOPMAN_EXPOSE_MOCK_CAPTURE=True,
            SHOPMAN_MOCK_PIX_AUTO_CONFIRM=False,
        ):
            self.assertEqual(shop_checks.check_mock_pix_confirm_conflict(None), [])
