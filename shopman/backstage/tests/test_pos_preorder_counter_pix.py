"""O saldo da encomenda em Pix no balcão (#2897), sem cobrança dupla.

Gesto de dinheiro tem uma tela só: o "Receber e entregar" cobra em Pix do jeito
que a venda de balcão cobra (intent Pix do pedido, QR, confirmação pelo caminho
canônico), e a entrega é o hand-over de sempre. O que estes testes prendem é o
dinheiro: o cliente nunca tem duas cobranças vivas, o Pix que não chega não
cancela a encomenda, e receber de outra forma cancela o Pix antes.
"""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

import pytest
from django.contrib.auth.models import Permission, User
from django.test import override_settings
from django.utils import timezone
from shopman.cashman import services as cash
from shopman.cashman.models import Entry, Terminal
from shopman.orderman.models import Directive, Order, OrderItem
from shopman.payman import PaymentService
from shopman.payman.models import PaymentIntent

from shopman.backstage.projections import preorders
from shopman.backstage.tests.pos_test_runtime import bind_station
from shopman.shop.adapters import payment_stripe
from shopman.shop.adapters.payment_types import PaymentResult
from shopman.shop.handlers.payment_timeout import PaymentTimeoutHandler
from shopman.shop.services import counter_pix, counter_takeover, operator_orders
from shopman.shop.services import payment as payment_svc
from shopman.shop.services.pix_confirmation import confirm_pix

pytestmark = [pytest.mark.django_db, pytest.mark.channels("web")]

ADAPTERS = {
    "pix": "shopman.shop.adapters.payment_mock",
    "card": "shopman.shop.adapters.payment_stripe",
    "link": "shopman.shop.adapters.payment_stripe",
    "cash": None,
    "external": None,
}
MOCK = {"SHOPMAN_PAYMENT_ADAPTERS": ADAPTERS, "SHOPMAN_ALLOW_MOCK_PAYMENT_ADAPTERS": True}
PIX_URL = "/api/v1/backstage/pos/preorders/{ref}/pix/"
HAND_OVER_URL = "/api/v1/backstage/pos/preorders/{ref}/hand-over/"


def _order(ref: str, *, payment: dict, total_q: int = 3600) -> Order:
    order = Order.objects.create(ref=ref, channel_ref="web", status="ready", total_q=total_q, data={
        "customer": {"name": "Ana Souza", "phone": "+5543999887766"},
        "fulfillment_type": "pickup",
        "delivery_date": timezone.localdate().isoformat(),
        "payment": payment,
    })
    OrderItem.objects.create(order=order, line_id="1", sku="PAO", name="Pão", qty=2, unit_price_q=total_q // 2,
                             line_total_q=total_q)
    return order


def _pay_at_pickup(ref: str, total_q: int = 3600) -> Order:
    """A encomenda "a pagar na retirada": dinheiro combinado, nada recebido."""
    return _order(ref, total_q=total_q, payment={
        "method": "cash", "collection": "on_delivery", "amount_q": total_q,
        "tenders": [{"method": "cash", "amount_q": total_q, "collection": "on_delivery", "status": "pending"}],
    })


def _pix_intents(order_ref: str):
    return list(PaymentIntent.objects.filter(order_ref=order_ref, method="pix").order_by("id"))


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


def _start_pix(client, order: Order):
    order.refresh_from_db()
    return client.post(
        PIX_URL.format(ref=order.ref),
        {"base_revision": operator_orders.operational_revision(order), "client_request_id": f"pix-{order.ref}"},
        content_type="application/json",
    )


def _hand_over(client, order: Order, *, tenders=None, request_id: str, cash_tendered_q=None):
    order.refresh_from_db()
    body = {"base_revision": operator_orders.operational_revision(order), "client_request_id": request_id}
    if tenders is not None:
        body["tenders"] = tenders
    if cash_tendered_q is not None:
        body["cash_tendered_q"] = cash_tendered_q
    return client.post(HAND_OVER_URL.format(ref=order.ref), body, content_type="application/json")


def _pay(intent: PaymentIntent, amount: str = "36.00", e2e: str = "E2E-BALCAO") -> None:
    """O cliente paga o QR: o mesmo caminho do webhook da Efí."""
    confirm_pix(txid=intent.gateway_id, e2e_id=e2e, amount=amount)


# ── O Pix nasce do jeito da venda ─────────────────────────────────────────


@override_settings(**MOCK)
def test_o_saldo_a_pagar_na_retirada_vira_um_pix_com_qr_no_formato_da_venda(balcao):
    order = _pay_at_pickup("CPX-1")

    response = _start_pix(balcao, order)

    assert response.status_code == 200, response.json()
    payment = response.json()["payment"]
    assert payment["method"] == "pix"
    assert payment["amount_q"] == 3600
    assert payment["status"] == "pending"
    assert payment["copy_paste"] and payment["qr_code"] and payment["expires_at"]
    order.refresh_from_db()
    data = order.data["payment"]
    assert data["method"] == "pix"
    assert "collection" not in data
    assert data["tenders"] == [{
        "method": "pix", "amount_q": 3600, "collection": "terminal", "status": "pending",
        "terminal_ref": Terminal.default().ref,
    }]
    marker = data["counter_pix"]
    assert marker["intent_ref"] == data["intent_ref"]
    assert marker["adopted"] is False
    assert marker["from"]["method"] == "cash"
    assert marker["from"]["collection"] == "on_delivery"
    assert [intent.status for intent in _pix_intents(order.ref)] == ["pending"]


@override_settings(**MOCK)
def test_o_pix_do_balcao_vence_no_prazo_de_balcao_e_nao_no_prazo_do_link(balcao):
    """Encomenda do PDV ganha o prazo do link no Pix remoto (P2-26); o do balcão não."""
    order = _pay_at_pickup("CPX-PRAZO")
    order.data["origin_channel"] = "pos"
    order.save(update_fields=["data"])

    response = _start_pix(balcao, order)

    assert response.status_code == 200, response.json()
    order.refresh_from_db()
    expires_at = PaymentService.get(order.data["payment"]["intent_ref"]).expires_at
    assert expires_at <= timezone.now() + timedelta(minutes=11)


@override_settings(**MOCK)
def test_pedir_o_pix_de_novo_devolve_o_mesmo_qr_e_nunca_cria_outra_cobranca(balcao):
    order = _pay_at_pickup("CPX-IDEM")

    first = _start_pix(balcao, order).json()["payment"]
    second = _start_pix(balcao, order)

    assert second.status_code == 200
    assert second.json()["payment"]["intent_ref"] == first["intent_ref"]
    assert len(_pix_intents(order.ref)) == 1


@override_settings(**MOCK)
def test_o_pix_online_vivo_do_cliente_e_o_mesmo_que_ele_paga_no_balcao(balcao):
    order = _order("CPX-ONLINE", payment={})
    intent = PaymentService.create_intent(order.ref, 3600, "pix", gateway="mock", gateway_id="txid-CPX-ONLINE")
    order.data["payment"] = {
        "method": "pix", "intent_ref": intent.ref, "amount_q": 3600, "copy_paste": "000201online",
        "qr_code": "data:image/png;base64,AAAA", "expires_at": (timezone.now() + timedelta(hours=1)).isoformat(),
    }
    order.save(update_fields=["data"])

    response = _start_pix(balcao, order)

    assert response.status_code == 200, response.json()
    assert response.json()["payment"]["intent_ref"] == intent.ref
    assert response.json()["payment"]["copy_paste"] == "000201online"
    assert len(_pix_intents(order.ref)) == 1
    order.refresh_from_db()
    assert order.data["payment"]["counter_pix"]["adopted"] is True
    assert PaymentService.get(intent.ref).status == "pending"


@override_settings(**MOCK)
def test_o_link_vivo_e_cancelado_no_provedor_antes_de_o_pix_nascer(balcao):
    order = _order("CPX-LINK", payment={})
    link = PaymentService.create_intent(order.ref, 3600, "link", gateway="stripe", gateway_id="cs_cpx",
                                        gateway_data={"checkout_session_id": "cs_cpx"})
    order.data["payment"] = {"method": "link", "intent_ref": link.ref, "amount_q": 3600,
                             "checkout_url": "https://checkout.stripe.com/c/pay/x"}
    order.save(update_fields=["data"])

    with (
        patch.object(payment_svc, "settle_from_gateway", return_value="unpaid"),
        patch.object(payment_stripe, "cancel", return_value=PaymentResult(success=True)) as cancel_remote,
    ):
        response = _start_pix(balcao, order)

    assert response.status_code == 200, response.json()
    cancel_remote.assert_called_once()
    assert PaymentService.get(link.ref).status == "cancelled"
    order.refresh_from_db()
    data = order.data["payment"]
    assert data["method"] == "pix"
    assert "counter_takeover" not in data
    assert data["counter_takeover_history"][0]["cancelled_intent_ref"] == link.ref
    # O link pago depois, por engano, continua sendo pagamento em dobro.
    assert counter_takeover.cancelled_by_takeover(order, link.ref) is True


@override_settings(**MOCK)
def test_o_cliente_que_acabou_de_pagar_online_nao_ganha_outro_pix(balcao):
    order = _order("CPX-PAGOU", payment={})
    link = PaymentService.create_intent(order.ref, 3600, "link", gateway="stripe", gateway_id="cs_pagou",
                                        gateway_data={"checkout_session_id": "cs_pagou"})
    order.data["payment"] = {"method": "link", "intent_ref": link.ref, "amount_q": 3600}
    order.save(update_fields=["data"])

    with patch.object(payment_svc, "settle_from_gateway", return_value="paid"):
        response = _start_pix(balcao, order)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "preorder_paid_online"
    assert _pix_intents(order.ref) == []


# ── A confirmação e a entrega ─────────────────────────────────────────────


@override_settings(**MOCK)
def test_pix_confirmado_a_encomenda_fica_paga_e_o_entregar_e_o_de_sempre(balcao):
    order = _pay_at_pickup("CPX-PAGO")
    intent_ref = _start_pix(balcao, order).json()["payment"]["intent_ref"]

    _pay(PaymentService.get(intent_ref))

    status = balcao.get(f"/api/v1/backstage/pos/payment/{order.ref}/status/").json()
    assert status["is_paid"] is True
    order.refresh_from_db()
    hand_over = preorders.build_counter_block(order).hand_over
    assert (hand_over.allowed, hand_over.needs_payment, hand_over.counter_pix) == (True, False, None)

    delivered = _hand_over(balcao, order, request_id="cpx-pago-entrega")

    assert delivered.status_code == 200, delivered.json()
    assert delivered.json()["received_q"] == 0
    order.refresh_from_db()
    assert order.status == Order.Status.COMPLETED
    # O Pix não passa pela gaveta: nada entra no livro-caixa como dinheiro.
    assert not Entry.objects.filter(order_ref=order.ref, kind="cod_settled").exists()


@override_settings(**MOCK)
def test_pix_que_nao_chega_receber_em_dinheiro_cancela_o_pix_antes(balcao):
    order = _pay_at_pickup("CPX-DINHEIRO")
    intent_ref = _start_pix(balcao, order).json()["payment"]["intent_ref"]
    order.refresh_from_db()
    hand_over = preorders.build_counter_block(order).hand_over
    assert hand_over.digital_charge_notice == "O Pix gerado no balcão será cancelado."
    assert hand_over.counter_pix["intent_ref"] == intent_ref

    response = _hand_over(
        balcao, order, tenders=[{"method": "cash", "amount_q": 3600}], cash_tendered_q=5000,
        request_id="cpx-dinheiro",
    )

    assert response.status_code == 200, response.json()
    assert PaymentService.get(intent_ref).status == "cancelled"
    order.refresh_from_db()
    assert order.status == Order.Status.COMPLETED
    assert order.data["payment"]["counter_takeover"]["cancelled_intent_ref"] == intent_ref
    assert list(Entry.objects.filter(order_ref=order.ref, kind="cod_settled").values_list("amount_q", flat=True)) == [3600]


@override_settings(**MOCK)
def test_o_pix_pago_depois_do_dinheiro_e_estornado_no_mesmo_meio(balcao):
    """O cliente pagou o QR no último segundo: pagou duas vezes, e o Pix volta sozinho."""
    order = _pay_at_pickup("CPX-TARDE")
    intent_ref = _start_pix(balcao, order).json()["payment"]["intent_ref"]
    _hand_over(balcao, order, tenders=[{"method": "cash", "amount_q": 3600}], request_id="cpx-tarde")

    with patch.object(counter_takeover, "refund_late_payment") as refund:
        _pay(PaymentService.get(intent_ref), e2e="E2E-TARDE")

    refund.assert_called_once()


@override_settings(**MOCK)
def test_pix_do_balcao_vencido_nao_cancela_a_encomenda(balcao):
    order = _pay_at_pickup("CPX-VENCEU")
    intent_ref = _start_pix(balcao, order).json()["payment"]["intent_ref"]
    order.refresh_from_db()
    assert counter_pix.governs(order) is True
    directive = Directive.objects.create(topic="payment.timeout", payload={
        "order_ref": order.ref, "intent_ref": intent_ref,
        "expires_at": (timezone.now() - timedelta(minutes=1)).isoformat(),
    })

    with patch.object(payment_svc, "settle_from_gateway", return_value="unpaid"):
        PaymentTimeoutHandler().handle(message=directive, ctx={})

    order.refresh_from_db()
    assert order.status == Order.Status.READY


@override_settings(**MOCK)
def test_vencido_o_pix_do_balcao_gera_outro_e_o_velho_morre_antes(balcao):
    order = _pay_at_pickup("CPX-OUTRO")
    first = _start_pix(balcao, order).json()["payment"]["intent_ref"]
    order.refresh_from_db()
    payment = dict(order.data["payment"])
    payment["expires_at"] = (timezone.now() - timedelta(minutes=1)).isoformat()
    order.data["payment"] = payment
    order.save(update_fields=["data"])

    response = _start_pix(balcao, order)

    assert response.status_code == 200, response.json()
    second = response.json()["payment"]["intent_ref"]
    assert second != first
    assert PaymentService.get(first).status == "cancelled"
    assert [intent.status for intent in _pix_intents(order.ref)] == ["cancelled", "pending"]
    order.refresh_from_db()
    assert counter_takeover.cancelled_by_takeover(order, first) is True


# ── O que o balcão não faz (e diz por quê) ────────────────────────────────


@override_settings(**MOCK)
def test_encomenda_com_parte_paga_nao_vira_pix_e_a_tela_sabe_por_que(balcao, operator):
    order = _pay_at_pickup("CPX-PARCIAL", total_q=3600)
    cash_intent = PaymentService.create_intent(order.ref, 1000, "cash")
    PaymentService.authorize(cash_intent.ref)
    PaymentService.capture(cash_intent.ref)
    payment = dict(order.data["payment"])
    payment["intent_ref"] = cash_intent.ref
    order.data["payment"] = payment
    order.save(update_fields=["data"])
    order.refresh_from_db()

    hand_over = preorders.build_counter_block(order, user=operator).hand_over
    response = _start_pix(balcao, order)

    assert (hand_over.allowed, hand_over.needs_payment, hand_over.amount_q) == (True, True, 2600)
    assert hand_over.pix_block_reason == counter_pix.PARTIAL_BALANCE_MESSAGE
    assert response.status_code == 400
    assert response.json()["detail"] == counter_pix.PARTIAL_BALANCE_MESSAGE
    assert _pix_intents(order.ref) == []


@override_settings(**MOCK)
def test_a_tela_desatualizada_nao_gera_pix(balcao):
    order = _pay_at_pickup("CPX-VELHA")

    response = balcao.post(PIX_URL.format(ref=order.ref), {"base_revision": "velha"}, content_type="application/json")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "preorder_changed"
    assert _pix_intents(order.ref) == []
