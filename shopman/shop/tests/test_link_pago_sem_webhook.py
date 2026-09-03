"""O pedido K65, em três provas.

Primeira venda real de link (03/09/2026): o cliente pagou no Stripe e a casa
ficou em "pending" para sempre, e o aviso saiu por e-mail com WhatsApp
cadastrado. Dois defeitos de código, um de painel (o webhook nunca chegou).
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from shopman.shop.adapters import payment_stripe
from shopman.shop.services import notification


def _order(*, phone, handle_type="", handle_ref=""):
    return SimpleNamespace(
        data={"customer": {"phone": phone, "email": "x@y.z"}},
        handle_type=handle_type,
        handle_ref=handle_ref,
    )


class TestWhatsAppRecebeTelefoneComMais:
    """Dígitos puros são `subscriber_id`; telefone vai em E.164 com o "+".

    O PDV grava "5543984049009" e o adapter tomava isso por subscriber_id —
    ManyChat: "Subscriber does not exist", cadeia caindo para o e-mail.
    """

    def test_telefone_do_pdv_sem_mais_vira_e164(self):
        assert notification._resolve_recipient(_order(phone="5543984049009"), "manychat") == "+5543984049009"

    def test_telefone_com_mais_continua_igual(self):
        assert notification._resolve_recipient(_order(phone="+5543984049009"), "manychat") == "+5543984049009"

    def test_telefone_formatado_e_normalizado(self):
        assert notification._resolve_recipient(_order(phone="(43) 98404-9009"), "manychat") == "+5543984049009"

    def test_subscriber_id_do_manychat_continua_puro(self):
        order = _order(phone="5543984049009", handle_type="manychat", handle_ref="123456789")
        assert notification._resolve_recipient(order, "manychat") == "123456789"

    def test_sem_telefone_nao_ha_destinatario(self):
        assert notification._resolve_recipient(_order(phone=""), "manychat") is None

    def test_o_adapter_nao_toma_o_telefone_por_subscriber(self):
        from shopman.shop.adapters import notification_manychat as mc

        config = {"api_token": "t", "resolver": "shopman.shop.tests.test_adapters._manychat_test_resolver"}
        # Com o "+", o adapter delega ao resolver (que aqui devolve 123456);
        # sem o "+", ele devolvia int("5543984049009") como se fosse subscriber.
        assert mc._resolve_subscriber("+5543999998888", config) == 123456
        assert mc._resolve_subscriber("5543984049009", config) == 5543984049009


@pytest.mark.django_db
class TestCapturaPromoveIntentPendente:
    """Link paga `automatic` no Stripe; sem webhook o intent fica `pending`.

    A reconciliação chamava `PaymentService.capture` direto e morria em
    `invalid_transition` (esperado `authorized`) — gateway pago, casa
    "aguardando", para sempre. A autorização é o mesmo fato que o webhook
    registraria, e agora a captura a grava antes.
    """

    def _intent(self):
        from shopman.payman import PaymentService

        intent = PaymentService.create_intent(
            order_ref="PDV-TEST-K65",
            amount_q=600,
            method="link",
            gateway="stripe",
            gateway_data={"checkout_session_id": "cs_test_k65"},
        )
        intent.gateway_id = "cs_test_k65"
        intent.save(update_fields=["gateway_id"])
        return intent

    def _stripe(self, status):
        stripe = MagicMock()
        stripe.PaymentIntent.retrieve.return_value = SimpleNamespace(
            id="pi_test_k65", status=status, latest_charge="ch_test_k65"
        )
        stripe.PaymentIntent.capture.return_value = SimpleNamespace(
            id="pi_test_k65", status="succeeded", latest_charge="ch_test_k65"
        )
        return stripe

    def test_gateway_succeeded_e_intent_pending_captura(self):
        intent = self._intent()
        with patch.object(payment_stripe, "_get_stripe", return_value=self._stripe("succeeded")), patch.object(
            payment_stripe, "gateway_payment_intent_id", return_value="pi_test_k65"
        ):
            result = payment_stripe.capture(intent.ref)

        assert result.success, result.message
        intent.refresh_from_db()
        assert intent.status == "captured"
        assert intent.gateway_id == "pi_test_k65"

    def test_gateway_requires_capture_e_intent_pending_captura_nos_dois_lados(self):
        intent = self._intent()
        stripe = self._stripe("requires_capture")
        with patch.object(payment_stripe, "_get_stripe", return_value=stripe), patch.object(
            payment_stripe, "gateway_payment_intent_id", return_value="pi_test_k65"
        ):
            result = payment_stripe.capture(intent.ref)

        assert result.success, result.message
        stripe.PaymentIntent.capture.assert_called_once()
        intent.refresh_from_db()
        assert intent.status == "captured"

    def test_intent_ja_autorizado_nao_autoriza_de_novo(self):
        from shopman.payman import PaymentService

        intent = self._intent()
        PaymentService.authorize(intent.ref, gateway_id="pi_test_k65")
        with patch.object(payment_stripe, "_get_stripe", return_value=self._stripe("succeeded")), patch.object(
            payment_stripe, "gateway_payment_intent_id", return_value="pi_test_k65"
        ):
            result = payment_stripe.capture(intent.ref)

        assert result.success, result.message
        intent.refresh_from_db()
        assert intent.status == "captured"


class TestRotuloDoPagamentoEmPortugues:
    def test_status_do_payman_vira_portugues(self):
        from shopman.backstage.presentation.status import payment_status_label

        assert payment_status_label("pending") == "Aguardando pagamento"
        assert payment_status_label("captured") == "Pago"
        assert payment_status_label("refunded") == "Reembolsado"
        assert payment_status_label("") == ""

    def test_status_desconhecido_nao_some(self):
        from shopman.backstage.presentation.status import payment_status_label

        assert payment_status_label("partially_refunded") == "partially_refunded"
