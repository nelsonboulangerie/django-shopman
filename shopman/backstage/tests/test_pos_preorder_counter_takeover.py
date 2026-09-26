"""Encomenda com Pix ou link pendente recebida no balcão — sem cobrança dupla.

Decisão do dono (26/09/2026). O gesto é o mesmo "Receber e entregar"; o que muda
é a ordem: perguntar ao provedor se o cliente já pagou, cancelar a cobrança dele
no provedor e no Payman, calar os avisos de cobrança, e só então receber no
turno. E se o provedor confirmar o pagamento DEPOIS, o dinheiro volta no mesmo
meio, sozinho, e o operador é avisado.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from django.contrib.auth.models import Permission, User
from django.test import override_settings
from django.utils import timezone
from shopman.cashman import services as cash
from shopman.cashman.models import Entry, Terminal
from shopman.orderman.models import Directive, Order, OrderItem
from shopman.payman import PaymentService

from shopman.backstage.models import OperatorAlert
from shopman.backstage.projections import preorders
from shopman.backstage.tests.pos_test_runtime import bind_station
from shopman.shop.adapters import fiscal_focusnfe, payment_mock, payment_stripe
from shopman.shop.adapters.payment_types import PaymentResult
from shopman.shop.services import counter_takeover, fiscal, operator_orders
from shopman.shop.services import notification as notification_svc
from shopman.shop.services import payment as payment_svc
from shopman.shop.services.pix_confirmation import confirm_pix

pytestmark = pytest.mark.django_db

STRIPE_SETTINGS = {
    "secret_key": "sk_test_fake",
    "webhook_secret": "whsec_test_fake",
    "capture_method": "automatic",
    "domain": "https://shop.example.com",
}
ADAPTERS = {
    "pix": "shopman.shop.adapters.payment_mock",
    "card": "shopman.shop.adapters.payment_stripe",
    "link": "shopman.shop.adapters.payment_stripe",
    "cash": None,
    "external": None,
}
URL = "/api/v1/backstage/pos/preorders/{ref}/hand-over/"


def _order(ref: str, *, payment: dict, total_q: int = 3600, channel_ref: str = "web", **extra) -> Order:
    order = Order.objects.create(ref=ref, channel_ref=channel_ref, status="ready", total_q=total_q, data={
        **extra,
        "customer": {"name": "Ana Souza", "phone": "+5543999887766"},
        "fulfillment_type": "pickup",
        "delivery_date": timezone.localdate().isoformat(),
        "payment": payment,
    })
    OrderItem.objects.create(order=order, line_id="1", sku="PAO", name="Pão", qty=2, unit_price_q=total_q // 2,
                             line_total_q=total_q)
    return order


def _pix_order(ref: str) -> tuple[Order, object]:
    order = _order(ref, payment={})
    intent = PaymentService.create_intent(order.ref, 3600, "pix", gateway="mock", gateway_id=f"txid-{ref}")
    order.data["payment"] = {
        "method": "pix", "intent_ref": intent.ref, "amount_q": 3600,
        "copy_paste": "000201...", "expires_at": (timezone.now() + timezone.timedelta(hours=1)).isoformat(),
    }
    order.save(update_fields=["data"])
    return order, intent


def _link_order(ref: str, *, session_id: str) -> tuple[Order, object]:
    order = _order(ref, payment={})
    intent = PaymentService.create_intent(order.ref, 3600, "link", gateway="stripe", gateway_id=session_id,
                                          gateway_data={"checkout_session_id": session_id})
    order.data["payment"] = {
        "method": "link", "intent_ref": intent.ref, "amount_q": 3600,
        "checkout_url": "https://checkout.stripe.com/c/pay/x",
    }
    order.save(update_fields=["data"])
    return order, intent


def _queued_notice(order: Order, template: str) -> Directive:
    return Directive.objects.create(
        topic="notification.send", status="queued",
        payload={"order_ref": order.ref, "template": template},
    )


def _cash_entries(order_ref: str):
    return list(Entry.objects.filter(order_ref=order_ref).values_list("kind", "amount_q"))


@pytest.fixture
def operator():
    user = User.objects.create_user("marina", password="x", is_staff=True)
    for codename in ("operate_pos", "manage_orders"):
        user.user_permissions.add(Permission.objects.get(codename=codename))
    return user


@pytest.fixture
def balcao(client, operator):
    cash.open_shift(operator=operator, float_q=10000)
    client.force_login(operator)
    bind_station(client, Terminal.default().ref)
    return client


def _hand_over(client, order: Order, *, tenders, request_id: str, cash_tendered_q=None):
    body = {"base_revision": operator_orders.operational_revision(order), "client_request_id": request_id,
            "tenders": tenders}
    if cash_tendered_q is not None:
        body["cash_tendered_q"] = cash_tendered_q
    return client.post(URL.format(ref=order.ref), body, content_type="application/json")


# ── O detalhe oferece o gesto e diz o que vai ser cancelado ───────────────


def test_o_detalhe_oferece_receber_o_pix_pendente_e_avisa_que_ele_sera_cancelado(operator):
    order, _ = _pix_order("DET-PIX")

    hand_over = preorders.build_preorder_detail(order.ref, user=operator).hand_over

    assert (hand_over.allowed, hand_over.needs_payment, hand_over.amount_q) == (True, True, 3600)
    assert hand_over.block_reason == ""
    assert hand_over.digital_charge_notice == "O Pix enviado ao cliente será cancelado."


@override_settings(SHOPMAN_PAYMENT_ADAPTERS=ADAPTERS)
def test_o_detalhe_do_link_avisa_que_o_link_sera_cancelado(operator):
    order, _ = _link_order("DET-LINK", session_id="cs_det")

    hand_over = preorders.build_preorder_detail(order.ref, user=operator).hand_over

    assert hand_over.allowed is True
    assert hand_over.digital_charge_notice == "O link de pagamento enviado ao cliente será cancelado."


def test_o_ifood_continua_de_fora(operator):
    order = _order("IFOOD-PIX", payment={"method": "pix", "intent_ref": "PAY-X"}, channel_ref="ifood",
                   ifood={"payments": {"prepaid_q": 0, "pending_q": 3600, "methods": []}})

    assert counter_takeover.pending_digital_method(order) == ""
    assert "iFood" in operator_orders.counter_hand_over_block(order)


# ── Pix da Efí pendente → balcão recebe ───────────────────────────────────


def test_pix_pendente_e_cancelado_e_o_balcao_recebe_em_dinheiro(balcao):
    order, intent = _pix_order("PIX-BALCAO")
    notice = _queued_notice(order, "payment_requested")
    unrelated = _queued_notice(order, "order_ready")

    response = _hand_over(balcao, order, tenders=[{"method": "cash", "amount_q": 3600}],
                          cash_tendered_q=5000, request_id="t-pix-1")

    assert response.status_code == 200, response.json()
    intent.refresh_from_db()
    order.refresh_from_db()
    assert intent.status == "cancelled"
    assert order.status == "completed"
    payment = order.data["payment"]
    assert payment["method"] == "cash"
    assert payment["counter_takeover"]["from_method"] == "pix"
    assert payment["counter_takeover"]["cancelled_intent_ref"] == intent.ref
    assert payment["counter_takeover"]["actor"]
    assert (payment["tendered_q"], payment["change_q"]) == (5000, 1400)
    assert _cash_entries(order.ref) == [("cod_settled", 3600)]
    assert payment_svc.balance_due_q(order) == 0
    notice.refresh_from_db()
    unrelated.refresh_from_db()
    assert notice.payload["notification_delivery"]["status"] == "skipped"
    assert notice.payload["notification_delivery"]["reason"] == "payment_taken_over_at_counter"
    assert "notification_delivery" not in unrelated.payload


def test_depois_do_balcao_a_cobranca_nao_e_reenviada(balcao):
    order, _ = _pix_order("PIX-SEM-REENVIO")
    _hand_over(balcao, order, tenders=[{"method": "cash", "amount_q": 3600}], request_id="t-pix-reenvio")
    order.refresh_from_db()

    refusal = notification_svc.payment_notice_refusal(order)

    assert refusal is not None and refusal.code == "payment_taken_over_at_counter"


def test_pix_pendente_sem_a_forma_do_balcao_nao_cancela_nada(balcao):
    order, intent = _pix_order("PIX-SEM-FORMA")

    response = _hand_over(balcao, order, tenders=None, request_id="t-pix-sem-forma")

    assert response.status_code == 400
    assert "Escolha como o cliente pagou" in response.json()["detail"]
    intent.refresh_from_db()
    assert intent.status == "pending"
    order.refresh_from_db()
    assert "counter_takeover" not in order.data["payment"]


def test_receber_direto_com_a_cobranca_viva_e_recusado(operator):
    order, _ = _pix_order("PIX-DIRETO")
    shift = cash.open_shift(operator=operator, float_q=0)

    with pytest.raises(ValueError, match="ainda está ativo"):
        operator_orders.hand_over_at_counter(order, cash_shift=shift, actor="pos:marina",
                                             tenders=[{"method": "cash", "amount_q": 3600}])


def test_falha_ao_cancelar_no_provedor_nao_muda_nada(balcao):
    order, intent = _pix_order("PIX-FALHA")
    notice = _queued_notice(order, "payment_requested")

    with patch.object(payment_mock, "cancel", return_value=PaymentResult(success=False, message="efí fora")):
        response = _hand_over(balcao, order, tenders=[{"method": "cash", "amount_q": 3600}], request_id="t-pix-falha")

    assert response.status_code == 409
    assert response.json()["detail"] == (
        "Não consegui cancelar o link do cliente. Tente de novo ou peça para ele pagar pelo link."
    )
    intent.refresh_from_db()
    order.refresh_from_db()
    notice.refresh_from_db()
    assert intent.status == "pending"
    assert order.status == "ready"
    assert "counter_takeover" not in order.data["payment"]
    assert _cash_entries(order.ref) == []
    assert "notification_delivery" not in notice.payload


def test_cliente_pagou_segundos_antes_o_balcao_nao_recebe_so_entrega(balcao, operator):
    order, intent = _pix_order("PIX-PAGOU")

    def efi_reconciles(intent_ref, **_):
        # O capture da Efí é "confere no gateway e, se CONCLUIDA, reconcilia".
        PaymentService.authorize(intent_ref)
        txn = PaymentService.capture(intent_ref)
        return PaymentResult(success=True, transaction_id="efi-e2e", amount_q=txn.amount_q)

    with (
        patch.object(payment_mock, "check_gateway_status", return_value="captured"),
        patch.object(payment_mock, "capture", side_effect=efi_reconciles),
    ):
        response = _hand_over(balcao, order, tenders=[{"method": "cash", "amount_q": 3600}], request_id="t-pix-pagou")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "preorder_paid_online"
    assert "acabou de pagar" in response.json()["detail"]
    intent.refresh_from_db()
    order.refresh_from_db()
    assert intent.status == "captured"
    assert "counter_takeover" not in order.data["payment"]
    assert _cash_entries(order.ref) == []
    # O detalhe agora oferece só "Entregar".
    hand_over = preorders.build_preorder_detail(order.ref, user=operator).hand_over
    assert (hand_over.allowed, hand_over.needs_payment, hand_over.digital_charge_notice) == (True, False, "")


def test_pix_que_chega_depois_do_balcao_e_estornado_no_pix_e_alerta(balcao):
    order, intent = _pix_order("PIX-TARDIO")
    _hand_over(balcao, order, tenders=[{"method": "cash", "amount_q": 3600}], request_id="t-pix-tardio")

    confirm_pix(txid=f"txid-{order.ref}", e2e_id="E2E-TARDIO", amount="36.00")

    booked = PaymentService.get_by_order(order.ref).get(gateway_data__booked_by="pix_confirmation")
    assert booked.status == "refunded"
    assert PaymentService.refunded_total(booked.ref) == 3600
    alert = OperatorAlert.objects.get(type="payment_after_cancel", order_ref=order.ref)
    assert alert.severity == "warning"
    assert "Devolvemos R$ 36,00 no mesmo Pix" in alert.message
    order.refresh_from_db()
    assert order.status == "completed"
    assert payment_svc.balance_due_q(order) == 0
    # O mesmo Pix reapresentado não devolve duas vezes.
    confirm_pix(txid=f"txid-{order.ref}", e2e_id="E2E-TARDIO", amount="36.00")
    assert PaymentService.refunded_total(booked.ref) == 3600


# ── Link do Stripe pendente → balcão recebe ───────────────────────────────


def _open_session(session_id: str):
    return SimpleNamespace(id=session_id, status="open", payment_intent=None)


@override_settings(SHOPMAN_PAYMENT_ADAPTERS=ADAPTERS, SHOPMAN_STRIPE=STRIPE_SETTINGS)
def test_link_pendente_expira_a_sessao_e_o_balcao_recebe_no_debito(balcao):
    order, intent = _link_order("LINK-BALCAO", session_id="cs_balcao")
    notice = _queued_notice(order, "payment_link_sent")
    stripe = MagicMock()
    stripe.checkout.Session.retrieve.return_value = _open_session("cs_balcao")

    with patch.object(payment_stripe, "_get_stripe", return_value=stripe):
        response = _hand_over(balcao, order, tenders=[{"method": "debit", "amount_q": 3600}], request_id="t-link-1")

    assert response.status_code == 200, response.json()
    stripe.checkout.Session.expire.assert_called_once_with("cs_balcao")
    intent.refresh_from_db()
    order.refresh_from_db()
    notice.refresh_from_db()
    assert intent.status == "cancelled"
    assert order.status == "completed"
    assert order.data["payment"]["method"] == "debit"
    assert order.data["payment"]["counter_takeover"]["from_method"] == "link"
    assert _cash_entries(order.ref) == []  # cartão não mexe na gaveta
    assert notice.payload["notification_delivery"]["reason"] == "payment_taken_over_at_counter"
    assert payment_svc.balance_due_q(order) == 0

    # A nota fiscal lê o meio EFETIVO: débito do balcão, não o link cancelado.
    forms = fiscal_focusnfe._payment_forms(fiscal._fiscal_payment(order, order.data))
    assert forms == [{"forma_pagamento": "04", "valor_pagamento": "36.00"}]


@override_settings(SHOPMAN_PAYMENT_ADAPTERS=ADAPTERS, SHOPMAN_STRIPE=STRIPE_SETTINGS)
def test_pagamento_do_link_que_chega_depois_do_balcao_e_estornado_no_cartao(balcao, client):
    order, intent = _link_order("LINK-TARDIO", session_id="cs_tardio")
    stripe = MagicMock()
    stripe.checkout.Session.retrieve.return_value = _open_session("cs_tardio")
    with patch.object(payment_stripe, "_get_stripe", return_value=stripe):
        assert _hand_over(balcao, order, tenders=[{"method": "cash", "amount_q": 3600}],
                          request_id="t-link-tardio").status_code == 200

    event = MagicMock()
    event.id = "evt_link_tardio"
    event.type = "payment_intent.succeeded"
    event.data.object = SimpleNamespace(id="pi_tardio", metadata={"shopman_ref": intent.ref})
    stripe = MagicMock()
    stripe.Webhook.construct_event.return_value = event
    stripe.PaymentIntent.retrieve.return_value = SimpleNamespace(status="succeeded", amount_received=3600)
    stripe.Refund.create.return_value = SimpleNamespace(id="re_tardio", amount=3600)
    with patch.object(payment_stripe, "_get_stripe", return_value=stripe):
        response = client.post("/api/webhooks/stripe/", data=json.dumps({"type": event.type}).encode(),
                               content_type="application/json", HTTP_STRIPE_SIGNATURE="valid-sig")

    assert response.status_code == 200
    kwargs = stripe.Refund.create.call_args.kwargs
    assert kwargs["payment_intent"] == "pi_tardio"
    assert kwargs["amount"] == 3600
    booked = PaymentService.get_by_order(order.ref).get(gateway_data__booked_by="counter_takeover")
    assert booked.status == "refunded"
    intent.refresh_from_db()
    assert intent.status == "cancelled"
    alert = OperatorAlert.objects.get(type="payment_after_cancel", order_ref=order.ref)
    assert "no mesmo cartão" in alert.message
    order.refresh_from_db()
    assert order.status == "completed"
    assert payment_svc.balance_due_q(order) == 0


@override_settings(SHOPMAN_PAYMENT_ADAPTERS=ADAPTERS, SHOPMAN_STRIPE=STRIPE_SETTINGS)
def test_autorizacao_do_link_depois_do_balcao_e_anulada(balcao):
    order, intent = _link_order("LINK-AUTORIZADO", session_id="cs_aut")
    stripe = MagicMock()
    stripe.checkout.Session.retrieve.return_value = _open_session("cs_aut")
    with patch.object(payment_stripe, "_get_stripe", return_value=stripe):
        assert _hand_over(balcao, order, tenders=[{"method": "cash", "amount_q": 3600}],
                          request_id="t-link-aut").status_code == 200

    stripe = MagicMock()
    stripe.PaymentIntent.retrieve.return_value = SimpleNamespace(status="requires_capture", amount_received=0)
    with patch.object(payment_stripe, "_get_stripe", return_value=stripe):
        assert counter_takeover.handle_late_stripe_payment(intent.ref, "pi_aut") is True

    stripe.PaymentIntent.cancel.assert_called_once_with("pi_aut")
    stripe.Refund.create.assert_not_called()
    assert "anulada" in OperatorAlert.objects.get(type="payment_after_cancel", order_ref=order.ref).message
