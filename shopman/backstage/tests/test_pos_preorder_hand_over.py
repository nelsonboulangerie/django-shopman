"""Encomendas do PDV — receber o saldo e entregar no balcão (ENCOMENDAS-PDV-PLAN, WP-E3).

O gesto é um só e a transação também: o acerto canônico (``settle_delivery_cash``,
no turno do terminal) e o avanço canônico (``advance_order`` → concluído), com o
``payment_gate`` valendo. Estes testes prendem o que o balcão não pode errar:
quanto cobrar (o total EFETIVO menos tudo o que já entrou, por qualquer forma),
onde o dinheiro entra, o troco, e que nada fica pela metade.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from django.contrib.auth.models import Permission, User
from django.utils import timezone
from shopman.cashman import services as cash
from shopman.cashman.models import Entry, Terminal
from shopman.orderman.models import Order, OrderItem
from shopman.payman import PaymentService

from shopman.backstage.projections import preorders
from shopman.backstage.tests.pos_test_runtime import bind_station
from shopman.shop.services import operator_orders
from shopman.shop.services import payment as payment_svc

pytestmark = pytest.mark.django_db


def _order(ref: str, *, status: str = "ready", channel_ref: str = "web", total_q: int = 3600,
           fulfillment_type: str = "pickup", **data_extra) -> Order:
    data = {
        "customer": {"name": "Ana Souza", "phone": "+5543999887766"},
        "fulfillment_type": fulfillment_type,
        "delivery_date": timezone.localdate().isoformat(),
    }
    data.update(data_extra)
    order = Order.objects.create(ref=ref, channel_ref=channel_ref, status=status, total_q=total_q, data=data)
    OrderItem.objects.create(order=order, line_id="1", sku="PAO", name="Pão", qty=2, unit_price_q=total_q // 2,
                             line_total_q=total_q)
    return order


@pytest.fixture
def operator():
    user = User.objects.create_user("marina", password="x", is_staff=True)
    for codename in ("operate_pos", "manage_orders"):
        user.user_permissions.add(Permission.objects.get(codename=codename))
    return user


@pytest.fixture
def shift(operator):
    return cash.open_shift(operator=operator, float_q=10000)


def _cash_entries(order_ref: str):
    return list(Entry.objects.filter(order_ref=order_ref).values_list("kind", "amount_q"))


# ── O saldo: total efetivo menos TODAS as formas ──────────────────────────


def test_saldo_soma_todas_as_formas_do_pagamento_misto():
    """Venda mista grava um intent por forma e nenhum ``payment.intent_ref``."""
    order = _order("MISTA")
    cash_intent = PaymentService.settle(order.ref, 1000, "cash", idempotency_key="t:mista:cash")
    pix_intent = PaymentService.settle(order.ref, 2600, "pix", idempotency_key="t:mista:pix", asserted_at_terminal=True)
    order.data["payment"] = {"method": "mixed", "tenders": [
        {"method": "cash", "amount_q": 1000, "status": "received", "intent_ref": cash_intent.ref},
        {"method": "pix", "amount_q": 2600, "status": "received", "intent_ref": pix_intent.ref},
    ]}
    order.save(update_fields=["data"])

    assert payment_svc.captured_balance_q(order) == 3600
    assert payment_svc.balance_due_q(order) == 0
    assert payment_svc.has_sufficient_captured_payment(order) is True


def test_misto_que_nao_cobre_o_total_nao_e_pago():
    order = _order("MISTA-CURTA")
    cash_intent = PaymentService.settle(order.ref, 1000, "cash", idempotency_key="t:curta:cash")
    order.data["payment"] = {"method": "mixed", "tenders": [
        {"method": "cash", "amount_q": 1000, "status": "received", "intent_ref": cash_intent.ref},
    ]}
    order.save(update_fields=["data"])

    assert payment_svc.balance_due_q(order) == 2600
    assert payment_svc.has_sufficient_captured_payment(order) is False


def test_pago_cobre_o_total_EFETIVO_do_pedido_ajustado():
    """O pedido ajustado (itens trocados depois) vale pelo total novo, não o selado."""
    order = _order("AJUSTADO", adjustment={
        "items": [{"line_id": "1", "sku": "PAO", "name": "Pão", "qty": "1", "unit_price_q": 1800, "line_total_q": 1800}],
        "total_q": 1800,
    })
    intent = PaymentService.settle(order.ref, 1800, "pix", idempotency_key="t:ajustado", asserted_at_terminal=True)
    order.data["payment"] = {"method": "pix", "intent_ref": intent.ref}
    order.save(update_fields=["data"])

    assert payment_svc.has_sufficient_captured_payment(order) is True
    assert payment_svc.balance_due_q(order) == 0


# ── Receber e entregar ────────────────────────────────────────────────────


def test_pagar_na_retirada_do_PDV_recebe_no_turno_e_entrega(operator, shift):
    order = _order("PDV-ENC", channel_ref="pdv", payment={
        "method": "cash", "collection": "on_delivery",
        "tenders": [{"method": "cash", "amount_q": 3600, "collection": "on_delivery", "status": "pending"}],
    })

    received = operator_orders.hand_over_at_counter(order, cash_shift=shift, actor="pos:marina")

    order.refresh_from_db()
    assert received == 3600
    assert order.status == "completed"
    assert order.data["payment"]["cod_settled_at"]
    assert _cash_entries(order.ref) == [("cod_settled", 3600)]
    assert payment_svc.balance_due_q(order) == 0


def test_loja_online_pago_na_retirada_aceita_a_forma_escolhida_no_balcao(operator, shift):
    """Combinou dinheiro, pagou no débito: a forma que vale é a do balcão."""
    order = _order("WEB-DINHEIRO", payment={"method": "cash"})

    operator_orders.hand_over_at_counter(
        order, cash_shift=shift, actor="pos:marina", tenders=[{"method": "debit", "amount_q": 3600}],
    )

    order.refresh_from_db()
    assert order.status == "completed"
    assert order.data["payment"]["method"] == "debit"
    assert _cash_entries(order.ref) == []  # cartão não mexe na gaveta
    assert payment_svc.has_sufficient_captured_payment(order) is True


def test_dinheiro_com_troco_grava_a_nota_e_o_troco_e_a_gaveta_recebe_so_a_venda(operator, shift):
    order = _order("TROCO", payment={"method": "cash"})

    operator_orders.hand_over_at_counter(
        order, cash_shift=shift, actor="pos:marina",
        tenders=[{"method": "cash", "amount_q": 3600}], cash_tendered_q=5000,
    )

    order.refresh_from_db()
    assert (order.data["payment"]["tendered_q"], order.data["payment"]["change_q"]) == (5000, 1400)
    assert _cash_entries(order.ref) == [("cod_settled", 3600)]


def test_o_valor_recebido_e_o_que_falta_no_pedido_ajustado(operator, shift):
    order = _order("AJUSTE-BALCAO", payment={"method": "cash"}, adjustment={
        "items": [{"line_id": "1", "sku": "PAO", "name": "Pão", "qty": "1", "unit_price_q": 1800, "line_total_q": 1800}],
        "total_q": 1800,
    })

    received = operator_orders.hand_over_at_counter(order, cash_shift=shift, actor="pos:marina")

    assert received == 1800
    assert _cash_entries(order.ref) == [("cod_settled", 1800)]


def test_ja_pago_so_entrega_e_dispensa_caixa_aberto():
    order = _order("JA-PAGO")
    intent = PaymentService.settle(order.ref, 3600, "pix", idempotency_key="t:ja-pago", asserted_at_terminal=True)
    order.data["payment"] = {"method": "pix", "intent_ref": intent.ref}
    order.save(update_fields=["data"])

    received = operator_orders.hand_over_at_counter(order, cash_shift=None, actor="pos:marina")

    order.refresh_from_db()
    assert (received, order.status) == (0, "completed")


def test_ja_pago_recusa_uma_segunda_cobranca(shift):
    order = _order("JA-PAGO-2")
    intent = PaymentService.settle(order.ref, 3600, "pix", idempotency_key="t:ja-pago-2", asserted_at_terminal=True)
    order.data["payment"] = {"method": "pix", "intent_ref": intent.ref}
    order.save(update_fields=["data"])

    with pytest.raises(ValueError, match="já está paga"):
        operator_orders.hand_over_at_counter(order, cash_shift=shift, actor="pos:marina",
                                             tenders=[{"method": "cash", "amount_q": 3600}])


def test_se_a_entrega_falha_o_recebimento_volta_junto(operator, shift):
    order = _order("ROLLBACK", payment={"method": "cash"})

    with patch.object(operator_orders, "advance_order", side_effect=ValueError("falhou")), pytest.raises(ValueError):
        operator_orders.hand_over_at_counter(order, cash_shift=shift, actor="pos:marina")

    order.refresh_from_db()
    assert order.status == "ready"
    assert not (order.data.get("payment") or {}).get("cod_settled_at")
    assert _cash_entries(order.ref) == []


@pytest.mark.parametrize(("status", "phrase"), [("preparing", "ainda não está pronta"), ("completed", "já foi entregue")])
def test_so_entrega_o_que_esta_pronto(shift, status, phrase):
    order = _order(f"S-{status}", status=status, payment={"method": "cash"})

    assert phrase in operator_orders.counter_hand_over_block(order)
    with pytest.raises(ValueError, match=phrase):
        operator_orders.hand_over_at_counter(order, cash_shift=shift, actor="pos:marina")


def test_pix_pendente_nao_recebe_no_balcao_sem_matar_a_cobranca_viva(shift):
    order = _order("PIX-PENDENTE")
    intent = PaymentService.create_intent(order.ref, 3600, "pix")
    order.data["payment"] = {"method": "pix", "intent_ref": intent.ref}
    order.save(update_fields=["data"])

    assert "pagamento online" in operator_orders.counter_hand_over_block(order)
    with pytest.raises(ValueError, match="pagamento online"):
        operator_orders.hand_over_at_counter(order, cash_shift=shift, actor="pos:marina",
                                             tenders=[{"method": "cash", "amount_q": 3600}])


def test_entrega_no_endereco_nao_sai_pelo_balcao(shift):
    order = _order("ENTREGA", fulfillment_type="delivery", payment={"method": "cash", "collection": "on_delivery"})

    assert "Gestor" in operator_orders.counter_hand_over_block(order)


def test_saldo_a_receber_sem_caixa_aberto_pede_o_caixa():
    order = _order("SEM-CAIXA", payment={"method": "cash"})

    with pytest.raises(ValueError, match="turno de caixa"):
        operator_orders.hand_over_at_counter(order, cash_shift=None, actor="pos:marina")


# ── O detalhe diz o gesto; a rota faz ─────────────────────────────────────


def test_o_detalhe_oferece_receber_e_entregar_com_o_valor_e_a_forma_combinada(operator):
    _order("DET-1", payment={"method": "cash"})

    detail = preorders.build_preorder_detail("DET-1", user=operator)

    assert detail.hand_over.allowed is True
    assert (detail.hand_over.needs_payment, detail.hand_over.amount_q) == (True, 3600)
    assert detail.hand_over.suggested_method == "cash"
    assert detail.revision == operator_orders.operational_revision(Order.objects.get(ref="DET-1"))
    assert detail.actor_id == operator.pk
    # A régua do Gestor decide o cancelamento da pronta; a tela só lê a frase.
    assert detail.cancel.allowed is False
    assert detail.cancel.block_reason


def test_o_detalhe_oferece_cancelar_a_encomenda_aceita_e_pede_pin_se_paga(operator):
    _order("DET-ACEITA", status="accepted", payment={"method": "cash"})
    paga = _order("DET-PAGA", status="accepted")
    intent = PaymentService.settle(paga.ref, 3600, "pix", idempotency_key="t:det-paga", asserted_at_terminal=True)
    paga.data["payment"] = {"method": "pix", "intent_ref": intent.ref}
    paga.save(update_fields=["data"])

    aceita = preorders.build_preorder_detail("DET-ACEITA", user=operator).cancel
    pago = preorders.build_preorder_detail("DET-PAGA", user=operator).cancel

    assert (aceita.allowed, aceita.requires_approval) == (True, False)
    assert (pago.allowed, pago.requires_approval) == (True, True)


def test_o_detalhe_do_ifood_manda_cancelar_pelo_gestor(operator):
    _order("IFOOD-DET", channel_ref="ifood", ifood={"payments": {"prepaid_q": 3600, "pending_q": 0, "methods": []}})

    detail = preorders.build_preorder_detail("IFOOD-DET", user=operator)

    assert detail.cancel.allowed is False
    assert "Gestor" in detail.cancel.block_reason
    # Pré-pago no iFood: não há o que receber, só entregar.
    assert (detail.hand_over.allowed, detail.hand_over.needs_payment) == (True, False)


@pytest.fixture
def balcao(client, operator, shift):
    client.force_login(operator)
    bind_station(client, Terminal.default().ref)
    return client


def test_a_rota_recebe_e_entrega(balcao):
    order = _order("ROTA-ENTREGA", payment={"method": "cash"})

    response = balcao.post(
        "/api/v1/backstage/pos/preorders/ROTA-ENTREGA/hand-over/",
        {"base_revision": operator_orders.operational_revision(order), "client_request_id": "t-rota-1",
         "tenders": [{"method": "cash", "amount_q": 3600}], "cash_tendered_q": 4000},
        content_type="application/json",
    )

    assert response.status_code == 200, response.json()
    assert response.json()["received_q"] == 3600
    assert response.json()["status"] == "completed"
    assert _cash_entries("ROTA-ENTREGA") == [("cod_settled", 3600)]


def test_a_rota_recusa_a_tela_desatualizada(balcao):
    _order("ROTA-VELHA", payment={"method": "cash"})

    response = balcao.post(
        "/api/v1/backstage/pos/preorders/ROTA-VELHA/hand-over/",
        {"base_revision": "revisao-velha", "client_request_id": "t-rota-2"},
        content_type="application/json",
    )

    assert response.status_code == 409
    assert _cash_entries("ROTA-VELHA") == []


def test_a_rota_exige_manage_orders(client, shift):
    caixa = User.objects.create_user("so-caixa", password="x", is_staff=True)
    caixa.user_permissions.add(Permission.objects.get(codename="operate_pos"))
    client.force_login(caixa)
    _order("ROTA-PERM", payment={"method": "cash"})

    response = client.post("/api/v1/backstage/pos/preorders/ROTA-PERM/hand-over/", {}, content_type="application/json")

    assert response.status_code == 403


# ── Reagendar: o detalhe diz se pode, e parte do combinado ────────────────


def test_o_detalhe_oferece_reagendar_a_encomenda_aceita_com_o_combinado(operator):
    _order("REAG-1", status="accepted", delivery_time_slot="slot-09")

    reschedule = preorders.build_preorder_detail("REAG-1", user=operator).reschedule

    assert reschedule.allowed is True
    assert (reschedule.date, reschedule.slot) == (timezone.localdate().isoformat(), "slot-09")
    assert reschedule.skus == ("PAO",)


def test_pronta_nao_reagenda_e_diz_por_que(operator):
    _order("REAG-PRONTA", status="ready")

    reschedule = preorders.build_preorder_detail("REAG-PRONTA", user=operator).reschedule

    assert reschedule.allowed is False
    assert "já está pronto" in reschedule.block_reason
