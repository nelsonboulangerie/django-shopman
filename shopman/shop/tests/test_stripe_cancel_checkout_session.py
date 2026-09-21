"""Cancelar pedido de cartão com a página do Stripe ainda aberta.

Antes do webhook ``checkout.session.completed`` o ``gateway_id`` do Payman é a
Checkout Session (``cs_...``). O cancelamento chamava
``PaymentIntent.cancel("cs_...")``, o Stripe recusava, e a página seguia aberta
por 24 h: o cliente ainda concluía o cartão e a autorização (captura manual)
ficava retida até vencer, sem ninguém anular nem ser avisado.

Duas pontas travadas aqui:
- o adapter EXPIRA a sessão aberta (e anula o PaymentIntent de sessão concluída);
- a autorização que chega pelo webhook para pedido já cancelado é anulada e alerta.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings
from rest_framework.test import APIClient
from shopman.payman import PaymentService

from shopman.backstage.models import OperatorAlert
from shopman.shop.adapters import payment_stripe
from shopman.shop.models import Channel
from shopman.shop.tests.test_stripe_checkout_session import (
    PAYMENT_ADAPTERS_STRIPE_CARD,
    STRIPE_SETTINGS,
    _commit_card_order,
)


def _session_intent(order_ref: str = "ORD-CS-1", *, session_id: str = "cs_test_aberta"):
    intent = PaymentService.create_intent(
        order_ref=order_ref,
        amount_q=1000,
        method="card",
        gateway="stripe",
        gateway_data={},
    )
    intent.gateway_id = session_id
    intent.gateway_data = {"checkout_session_id": session_id, "checkout_url": "https://checkout.stripe.com/x"}
    intent.save(update_fields=["gateway_id", "gateway_data"])
    return intent


def _stripe_with_session(*sessions):
    stripe = MagicMock()
    stripe.checkout.Session.retrieve.side_effect = list(sessions)
    return stripe


@override_settings(SHOPMAN_STRIPE=STRIPE_SETTINGS, SHOPMAN_PAYMENT_ADAPTERS=PAYMENT_ADAPTERS_STRIPE_CARD)
class StripeCancelCheckoutSessionTests(TestCase):
    def test_sessao_aberta_e_expirada_nao_cancelada_como_payment_intent(self) -> None:
        intent = _session_intent()
        stripe = _stripe_with_session(SimpleNamespace(status="open", payment_intent=None))

        with patch.object(payment_stripe, "_get_stripe", return_value=stripe):
            result = payment_stripe.cancel(intent.ref)

        assert result.success is True
        stripe.checkout.Session.expire.assert_called_once_with("cs_test_aberta")
        stripe.PaymentIntent.cancel.assert_not_called()
        intent.refresh_from_db()
        assert intent.status == "cancelled"

    def test_sessao_concluida_anula_o_payment_intent_dela(self) -> None:
        intent = _session_intent(session_id="cs_test_concluida")
        stripe = _stripe_with_session(SimpleNamespace(status="complete", payment_intent="pi_da_sessao"))

        with patch.object(payment_stripe, "_get_stripe", return_value=stripe):
            result = payment_stripe.cancel(intent.ref)

        assert result.success is True
        stripe.checkout.Session.expire.assert_not_called()
        stripe.PaymentIntent.cancel.assert_called_once_with("pi_da_sessao")

    def test_sessao_ja_expirada_nao_chama_nada(self) -> None:
        intent = _session_intent(session_id="cs_test_vencida")
        stripe = _stripe_with_session(SimpleNamespace(status="expired", payment_intent=None))

        with patch.object(payment_stripe, "_get_stripe", return_value=stripe):
            result = payment_stripe.cancel(intent.ref)

        assert result.success is True
        stripe.checkout.Session.expire.assert_not_called()
        stripe.PaymentIntent.cancel.assert_not_called()

    def test_cliente_conclui_entre_a_leitura_e_o_expire(self) -> None:
        intent = _session_intent(session_id="cs_test_corrida")
        stripe = _stripe_with_session(
            SimpleNamespace(status="open", payment_intent=None),
            SimpleNamespace(status="complete", payment_intent="pi_da_corrida"),
        )
        stripe.checkout.Session.expire.side_effect = Exception("session is not open")

        with patch.object(payment_stripe, "_get_stripe", return_value=stripe):
            result = payment_stripe.cancel(intent.ref)

        assert result.success is True
        stripe.PaymentIntent.cancel.assert_called_once_with("pi_da_corrida")

    def test_sessao_concluida_sem_payment_intent_nao_jura_cancelamento(self) -> None:
        intent = _session_intent(session_id="cs_test_sem_pi")
        stripe = _stripe_with_session(SimpleNamespace(status="complete", payment_intent=None))

        with patch.object(payment_stripe, "_get_stripe", return_value=stripe):
            result = payment_stripe.cancel(intent.ref)

        assert result.success is False
        intent.refresh_from_db()
        assert intent.status == "pending"


@override_settings(SHOPMAN_STRIPE=STRIPE_SETTINGS, SHOPMAN_PAYMENT_ADAPTERS=PAYMENT_ADAPTERS_STRIPE_CARD)
class StripeAuthorizationAfterCancelWebhookTests(TestCase):
    URL = "/api/webhooks/stripe/"

    def setUp(self) -> None:
        super().setUp()
        self.client = APIClient()
        Channel.objects.create(ref="web", name="Web", is_active=True)

    def test_autorizacao_que_chega_para_pedido_cancelado_e_anulada_e_alerta(self) -> None:
        order = _commit_card_order()
        order.transition_status("cancelled", actor="test")
        intent = _session_intent(order.ref, session_id="cs_test_tardia")
        order.refresh_from_db()
        order.data["payment"] = {"method": "card", "intent_ref": intent.ref}
        order.save(update_fields=["data", "updated_at"])

        event = MagicMock()
        event.id = "evt_tardia"
        event.type = "checkout.session.completed"
        session = MagicMock()
        session.id = "cs_test_tardia"
        session.payment_intent = "pi_tardia"
        session.metadata = {"shopman_ref": intent.ref}
        event.data.object = session

        stripe = MagicMock()
        stripe.Webhook.construct_event.return_value = event
        with patch.object(payment_stripe, "_get_stripe", return_value=stripe):
            resp = self.client.post(
                self.URL,
                data=json.dumps({"type": "checkout.session.completed"}).encode(),
                content_type="application/json",
                HTTP_STRIPE_SIGNATURE="valid-sig",
            )

        assert resp.status_code == 200
        stripe.PaymentIntent.cancel.assert_called_once_with("pi_tardia")
        intent.refresh_from_db()
        assert intent.status == "cancelled"
        alert = OperatorAlert.objects.get(type="payment_after_cancel", order_ref=order.ref)
        assert alert.severity == "warning"
        assert "anulada" in alert.message

    def test_anulacao_recusada_abre_alerta_critico(self) -> None:
        order = _commit_card_order()
        order.transition_status("cancelled", actor="test")
        intent = _session_intent(order.ref, session_id="cs_test_recusa")
        order.refresh_from_db()
        order.data["payment"] = {"method": "card", "intent_ref": intent.ref}
        order.save(update_fields=["data", "updated_at"])

        event = MagicMock()
        event.id = "evt_recusa"
        event.type = "checkout.session.completed"
        session = MagicMock()
        session.id = "cs_test_recusa"
        session.payment_intent = "pi_recusa"
        session.metadata = {"shopman_ref": intent.ref}
        event.data.object = session

        stripe = MagicMock()
        stripe.Webhook.construct_event.return_value = event
        stripe.PaymentIntent.cancel.side_effect = Exception("stripe down")
        with patch.object(payment_stripe, "_get_stripe", return_value=stripe):
            resp = self.client.post(
                self.URL,
                data=json.dumps({"type": "checkout.session.completed"}).encode(),
                content_type="application/json",
                HTTP_STRIPE_SIGNATURE="valid-sig",
            )

        assert resp.status_code == 200
        intent.refresh_from_db()
        assert intent.status == "authorized"
        alert = OperatorAlert.objects.get(type="payment_after_cancel", order_ref=order.ref)
        assert alert.severity == "critical"
