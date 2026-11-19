"""Tentar o estorno de novo fora do cancelado (#2727, itens 1 a 4; segue o WP-G13).

O G13 deu o gesto ao estorno do pedido CANCELADO. O que falhava fora dele (a devolução
registrada, a encomenda editada que ficou mais barata, o Pix que chegou depois de a
cobrança morrer) seguia na faixa com "o suporte conclui". Esta suíte prende:

- a régua do valor fora do cancelado é a do estorno automático de cada caso
  (``payment.overpaid_q``: a devolução e a edição), com o mesmo gesto, a mesma
  assinatura e a mesma regra de chave do G13;
- o mesmo dinheiro nunca é pedido por dois caminhos: o que a gaveta devolve não
  volta também pelo Pix, e o estorno automático que esgotou sem resposta tem a
  chave reapresentada;
- o Pix que chegou depois de a cobrança morrer volta pelo gateway da cobrança que
  ele substitui, e não é lido como maquininha;
- o aviso do sino diz o que fazer: no Gestor, quando o pedido tem o botão; o
  suporte, quando não tem;
- a recusa do gateway chega ao balcão na língua do balcão, também aqui.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.contrib.auth.models import Permission
from django.test import override_settings
from django.urls import reverse
from shopman.orderman.models import Directive, Order, OrderItem
from shopman.payman import PaymentService
from shopman.payman.models import PaymentTransaction

from shopman.backstage.models import OperatorAlert
from shopman.backstage.projections.order_queue import build_operator_order
from shopman.backstage.services import refund_retry
from shopman.shop.adapters import payment_mock
from shopman.shop.handlers.returns import ReturnService
from shopman.shop.models import Shop
from shopman.shop.services import order_composition, order_edit
from shopman.shop.services import payment as payment_service
from shopman.shop.services.pix_confirmation import _book_pix_outside_charge

pytestmark = [
    pytest.mark.django_db,
    pytest.mark.channels("web"),
    pytest.mark.usefixtures("_mock_gateway"),
]

SIGN = "shopman.backstage.api.operations.pos_tabs_service.validate_manager_override"
ADAPTER = "shopman.shop.services.payment._adapter_for_persisted_intent"
APPROVAL = {"username": "gerente", "pin": "SYNTHETIC-NOT-A-PIN"}
NO_SUPPORT = "O suporte"


@pytest.fixture
def _mock_gateway():
    Shop.objects.create(name="Padaria do estorno fora do cancelado")
    with override_settings(
        SHOPMAN_PAYMENT_ADAPTERS={
            "pix": "shopman.shop.adapters.payment_mock",
            "card": "shopman.shop.adapters.payment_mock",
            "cash": None,
            "external": None,
        }
    ):
        yield


@pytest.fixture
def operador(client, django_user_model):
    user = django_user_model.objects.create_user(username="caixa-devolucao", is_staff=True)
    user.user_permissions.add(Permission.objects.get(codename="manage_orders", content_type__app_label="shop"))
    client.force_login(user)
    return user


@pytest.fixture
def gerente(django_user_model):
    return django_user_model.objects.create_user(username="joyce", first_name="Joyce", is_staff=True)


class Gateway:
    """Dublê do adapter: recusa, fica mudo ou devolve pelo simulador, anotando cada chamada."""

    def __init__(self, mode: str = "accept"):
        self.mode = mode
        self.calls: list[dict] = []

    def refund(self, intent_ref, *, amount_q=None, reason="", idempotency_key="", **config):
        self.calls.append({"intent_ref": intent_ref, "amount_q": amount_q, "key": idempotency_key})
        if self.mode == "refuse":
            return SimpleNamespace(success=False, message="saldo insuficiente na conta", error_code="E_DECLINED")
        if self.mode == "silent":
            raise TimeoutError("gateway mudo")
        return payment_mock.refund(intent_ref, amount_q=amount_q, reason=reason, idempotency_key=idempotency_key)


def _paid_pix(ref: str, *, total_q: int = 3000, status: str = "delivered", pix_q: int | None = None, **data) -> Order:
    """Pedido pago no Pix pela loja (gateway de simulação), entregue. ``pix_q``: a parte no Pix."""
    order = Order.objects.create(
        ref=ref, channel_ref="web", session_key=f"s-{ref}", status=status, total_q=total_q,
        data={
            "customer": {"name": f"Cliente {ref}"},
            "fulfillment_type": "pickup",
            "payment": {"method": "pix", "intent_ref": f"INT-{ref}"},
            **data,
        },
    )
    OrderItem.objects.create(
        order=order, line_id=f"{ref}-1", sku="PAO", name="Pão", qty=3, unit_price_q=total_q // 3, line_total_q=total_q,
    )
    PaymentService.create_intent(order.ref, total_q if pix_q is None else pix_q, "pix", gateway="mock", ref=f"INT-{ref}")
    PaymentService.authorize(f"INT-{ref}", gateway_id=f"gw-{ref}")
    PaymentService.capture(f"INT-{ref}")
    return order


def _registered_return(order: Order, *, refund_q: int = 1000) -> Order:
    """A devolução de um pão registrada no pedido (o que o WP-G12 grava antes do estorno)."""
    order.data["returns"] = [{
        "type": "partial", "items": [{"line_id": f"{order.ref}-1", "sku": "PAO", "qty": "1", "refund_q": refund_q}],
        "refund_total_q": refund_q, "refund_processed": False, "stock_receipt_version": 1, "stock_processed": True,
    }]
    order.save(update_fields=["data", "updated_at"])
    return order


def _process_return(order: Order, mode: str, *, refund_q: int = 1000) -> dict:
    """O estorno da devolução pelo caminho de verdade, com o gateway no modo pedido."""
    with patch(ADAPTER, return_value=Gateway(mode)):
        result = ReturnService.process_refund(order, refund_q, "return.process", refund_reference=f"return:{order.ref}:0")
    order.refresh_from_db()
    return result


def _return_refused(ref: str, *, refund_q: int = 1000) -> Order:
    """WP-G12: a devolução de um pão registrada, e o estorno dela recusado pelo gateway.

    Pelo caminho de verdade: ``ReturnService.process_refund`` chama o ``payment.refund``
    com a chave da devolução, o gateway recusa e o ``payment.refund`` abre o aviso.
    """
    order = _registered_return(_paid_pix(ref), refund_q=refund_q)
    _process_return(order, "refuse", refund_q=refund_q)
    return order


def _edit_refused(ref: str) -> Order:
    """Encomenda de R$ 30,00 editada para R$ 20,00, e o estorno parcial recusado pelo gateway."""
    order = _paid_pix(ref, status="confirmed")
    order.data[order_composition.KEY] = {
        "items": [{"line_id": f"{ref}-1", "sku": "PAO", "name": "Pão", "qty": "2", "unit_price_q": 1000,
                   "line_total_q": 2000}],
        "total_q": 2000,
        "source": "pos:edit",
    }
    order.save(update_fields=["data", "updated_at"])
    with patch(ADAPTER, return_value=Gateway("refuse")):
        order_edit._refund_gateway(order.ref, amount_q=1000, idempotency_key=f"order-edit:{ref}:1")
    order.refresh_from_db()
    return order


def _retry(client, user, order, *, key=None, base=None, **body):
    payload = {"expected_actor_id": user.pk, "base_revision": base or refund_retry.revision(order), **body}
    return client.post(
        reverse("api-backstage-order-refund-retry", args=[order.ref]), payload,
        content_type="application/json", HTTP_IDEMPOTENCY_KEY=key or str(uuid.uuid4()),
    )


def _refund_line(order: Order, user=None):
    detail = build_operator_order(order, user=user)
    return detail, {item.key: item for item in detail.pending}.get("refund")


def _bell(order: Order) -> str:
    """O texto do aviso do sino (sem a linha de deduplicação que o registro guarda)."""
    alert = OperatorAlert.objects.get(type="payment_refund_failed", order_ref=order.ref, resolved_at__isnull=True)
    return alert.message.split("\n\nDedupe:")[0]


def _refunds(intent_ref: str):
    return PaymentTransaction.objects.filter(intent__ref=intent_ref, type="refund")


# ── Item 1: a devolução registrada ───────────────────────────────────────────


def test_devolucao_que_falhou_ganha_o_gesto_com_o_valor_da_devolucao(client, operador, gerente):
    order = _return_refused("DEV-2727")

    # A régua é a do estorno automático da devolução: o que entrou a mais do que o
    # pedido vale agora (``overpaid_q``), e não o pedido inteiro.
    assert payment_service.overpaid_q(order) == 1000
    current = refund_retry.plan(order)
    assert (current.failed, current.block_reason, current.amount_q, current.method) == (True, "", 1000, "pix")
    assert [(leg.intent_ref, leg.amount_q) for leg in current.legs] == [("INT-DEV-2727", 1000)]

    detail, line = _refund_line(order, operador)
    assert (line.tone, line.label) == ("error", "Estorno não saiu")
    assert line.reason == (
        "A devolução de R$ 10,00 não chegou ao cliente. Tentar de novo pede esse estorno outra vez "
        "ao Pix do cliente, com a autorização de um gerente."
    )
    assert NO_SUPPORT not in line.reason
    assert [(action.ref, action.enabled) for action in line.actions] == [("refund-retry", True)]
    assert any(action.ref == "refund-retry" for action in detail.actions)

    # O sino leva ao Gestor: o pedido tem o botão.
    assert payment_service.REFUND_FAILED_RETRY_HERE in _bell(order)
    assert "O suporte recebeu" not in _bell(order)

    gateway = Gateway()
    key = str(uuid.uuid4())
    with patch(SIGN, return_value=gerente), patch(ADAPTER, return_value=gateway):
        resp = _retry(client, operador, order, key=key, manager_approval=APPROVAL)

    assert resp.status_code == 200, resp.content
    assert resp.json()["refund"] == {"outcome": "refunded", "amount_q": 1000, "refunded_q": 1000, "message": ""}
    # Só a devolução volta, com a chave da tentativa (o automático foi RECUSADO: nada saiu).
    assert [(call["amount_q"], call["key"]) for call in gateway.calls] == [
        (1000, refund_retry.fresh_gateway_key(order.ref, "INT-DEV-2727", key)),
    ]
    assert PaymentService.refunded_total("INT-DEV-2727") == 1000
    order.refresh_from_db()
    assert payment_service.captured_balance_q(order) == 2000
    assert not OperatorAlert.objects.filter(type="payment_refund_failed", order_ref=order.ref, resolved_at__isnull=True)
    assert not any(item["key"] == "refund" for item in resp.json()["order"]["pending"])

    # O que o pedido ainda vale não se pede de novo.
    with patch(SIGN, return_value=gerente), patch(ADAPTER, return_value=gateway):
        again = _retry(client, operador, order, manager_approval=APPROVAL)
    assert again.status_code == 409, again.content
    assert len(gateway.calls) == 1
    assert PaymentService.refunded_total("INT-DEV-2727") == 1000


def test_devolucao_recusada_de_novo_fala_a_lingua_do_balcao(client, operador, gerente):
    """Item 4: a frase do gateway (escrita para o Admin) fica no evento; a linha lê a do balcão."""
    order = _return_refused("DEV-2727-RECUSA")

    with patch(SIGN, return_value=gerente), patch(ADAPTER, return_value=Gateway("refuse")):
        resp = _retry(client, operador, order, manager_approval=APPROVAL)

    assert resp.status_code == 200, resp.content
    answer = "O Pix não aceitou o estorno. Nada foi devolvido ao cliente. Chame o suporte."
    assert resp.json()["refund"]["message"] == answer
    line = next(item for item in resp.json()["order"]["pending"] if item["key"] == "refund")
    assert line["failure"].endswith(f": {answer}")
    assert "gateway" not in line["failure"].lower() and "Resposta (" not in line["failure"]
    (attempt,) = order.events.filter(type=refund_retry.EVENT_TYPE)
    assert attempt.payload["gateway_message"].startswith("O estorno foi recusado (gateway de teste)")
    timeline = {event["event_type"]: event for event in resp.json()["order"]["timeline"]}
    assert timeline["payment.refund_retry"]["detail"].endswith(f"não saiu: {answer}")


def test_estorno_automatico_da_devolucao_que_esgotou_tem_a_chave_reapresentada(client, operador, gerente):
    """A devolução caiu em falha transiente até esgotar: pode ter saído. A 1ª tentativa usa a chave DELA."""
    order = _paid_pix("DEV-2727-ESGOTOU")
    order.data["returns"] = [{"type": "partial", "refund_total_q": 1000, "items": []}]
    order.save(update_fields=["data", "updated_at"])
    Directive.objects.create(
        topic="payment.refund", status="failed", last_error="refund gateway error: timeout",
        payload={"order_ref": order.ref, "amount_q": 1000, "idempotency_key": f"return:{order.ref}:0"},
    )
    payment_service.alert_refund_failed(order, f"INT-{order.ref}", 1000, "tentativas de estorno esgotadas")
    gateway = Gateway()

    with patch(SIGN, return_value=gerente), patch(ADAPTER, return_value=gateway):
        resp = _retry(client, operador, order, manager_approval=APPROVAL)

    assert resp.status_code == 200, resp.content
    assert [(call["amount_q"], call["key"]) for call in gateway.calls] == [(1000, f"return:{order.ref}:0")]
    assert _refunds(f"INT-{order.ref}").count() == 1


# ── Item 1: a encomenda editada que ficou mais barata ────────────────────────


def test_encomenda_editada_que_ficou_mais_barata_ganha_o_gesto_com_a_diferenca(client, operador, gerente):
    order = _edit_refused("EDIT-2727")

    assert payment_service.overpaid_q(order) == 1000
    _detail, line = _refund_line(order, operador)
    assert line.reason == (
        "A devolução de R$ 10,00 não chegou ao cliente. Tentar de novo pede esse estorno outra vez "
        "ao Pix do cliente, com a autorização de um gerente."
    )
    assert [(action.ref, action.enabled) for action in line.actions] == [("refund-retry", True)]
    assert payment_service.REFUND_FAILED_RETRY_HERE in _bell(order)

    gateway = Gateway()
    with patch(SIGN, return_value=gerente), patch(ADAPTER, return_value=gateway):
        resp = _retry(client, operador, order, manager_approval=APPROVAL)

    assert resp.status_code == 200, resp.content
    assert resp.json()["refund"]["refunded_q"] == 1000
    assert [call["amount_q"] for call in gateway.calls] == [1000]
    order.refresh_from_db()
    assert payment_service.overpaid_q(order) == 0
    assert payment_service.captured_balance_q(order) == 2000


# ── Nunca o mesmo dinheiro por dois caminhos ─────────────────────────────────


def test_o_que_a_gaveta_devolve_nao_volta_tambem_pelo_pix(operador):
    """Pago R$ 10,00 em dinheiro e R$ 20,00 no Pix; devolvidos R$ 10,00.

    A lista da gaveta do PDV já devolve esses R$ 10,00 em dinheiro. O Pix não pede o
    mesmo valor outra vez: o gesto não aparece, e quem conclui segue sendo a casa.
    """
    order = _paid_pix("MISTO-2727", total_q=3000, pix_q=2000)
    PaymentService.settle(order.ref, 1000, "cash", idempotency_key=f"test:{order.ref}:cash")
    order.data["payment"]["tenders"] = [
        {"method": "cash", "amount_q": 1000, "status": "received",
         "intent_ref": PaymentService.get_by_order(order.ref).get(method="cash").ref},
        {"method": "pix", "amount_q": 2000, "status": "received", "intent_ref": f"INT-{order.ref}"},
    ]
    order.data["returns"] = [{"type": "partial", "refund_total_q": 1000, "items": []}]
    order.save(update_fields=["data", "updated_at"])
    payment_service.alert_refund_failed(order, f"INT-{order.ref}", 1000, "recusado pelo gateway")

    assert payment_service.overpaid_q(order) == 1000
    (cash,) = [item for item in payment_service.pending_cash_refunds() if item.order_ref == order.ref]
    assert cash.amount_q == 1000
    assert payment_service.gateway_refund_owed_q(order) == 0
    assert refund_retry.plan(order).failed is False

    detail, line = _refund_line(order, operador)
    assert line.actions == ()
    assert not any(action.ref == "refund-retry" for action in detail.actions)
    # Sem o botão, o sino segue com o suporte.
    assert payment_service.REFUND_FAILED_SUPPORT in _bell(order)


# ── Item 2: o Pix que chegou depois de a cobrança morrer ─────────────────────


def _cancelled_with_late_pix(ref: str) -> tuple[Order, str]:
    """Pedido cancelado com a cobrança Pix vencida, e o Pix pago depois, no QR velho.

    O registro é o de verdade (``pix_confirmation._book_pix_outside_charge``): um intent
    novo, SEM gateway (a cobrança morta ocupa o par único), com a cobrança morta em
    ``superseded_intent_ref``. O estorno automático foi recusado.
    """
    order = Order.objects.create(
        ref=ref, channel_ref="web", session_key=f"s-{ref}", status="cancelled", total_q=2200,
        data={"customer": {"name": "Ana"}, "fulfillment_type": "pickup",
              "payment": {"method": "pix", "intent_ref": f"INT-{ref}"}},
    )
    OrderItem.objects.create(order=order, line_id="1", sku="PAO", name="Pão", qty=1, unit_price_q=2200, line_total_q=2200)
    dead = PaymentService.create_intent(order.ref, 2200, "pix", gateway="mock", gateway_id=f"txid-{ref}", ref=f"INT-{ref}")
    PaymentService.cancel(dead.ref, reason="expired")
    dead.refresh_from_db()
    booked_ref, _already = _book_pix_outside_charge(
        order, dead, txid=f"txid-{ref}", e2e_id=f"E2E-{ref}", amount_q=2200, confirmation_source={},
    )
    with patch.object(payment_mock, "refund", return_value=SimpleNamespace(success=False, message="recusado", error_code="E")):
        payment_service.refund(order)
    order.refresh_from_db()
    return order, booked_ref


def test_pix_tardio_volta_pelo_gateway_da_cobranca_que_ele_substitui(client, operador, gerente):
    order, booked_ref = _cancelled_with_late_pix("TARDIO-2727")
    booked = PaymentService.get(booked_ref)

    # O registro: sem gateway, com a cobrança morta ao lado.
    assert (booked.gateway, booked.gateway_data["booked_by"]) == ("", "pix_confirmation")
    assert booked.gateway_data["superseded_intent_ref"] == f"INT-{order.ref}"
    # Não é maquininha: o PDV não pede estorno na maquininha de um Pix que nunca passou por ela.
    assert order_edit.refund_route(booked) == order_edit.ROUTE_GATEWAY
    assert payment_service.card_machine_refund_due(order) == (0, [])

    current = refund_retry.plan(order)
    assert (current.block_reason, current.amount_q) == ("", 2200)
    assert [leg.intent_ref for leg in current.legs] == [booked_ref]
    _detail, line = _refund_line(order, operador)
    assert [(action.ref, action.enabled) for action in line.actions] == [("refund-retry", True)]
    assert payment_service.REFUND_FAILED_RETRY_HERE in _bell(order)

    # Sem dublê no adapter: o estorno segue o gateway da cobrança substituída (o simulador).
    with patch(SIGN, return_value=gerente):
        resp = _retry(client, operador, order, manager_approval=APPROVAL)

    assert resp.status_code == 200, resp.content
    assert resp.json()["refund"]["outcome"] == "refunded"
    assert PaymentService.refunded_total(booked_ref) == 2200
    assert resp.json()["order"]["cancelled_money"]["state"] == "refunded"


def test_o_gateway_aceita_o_estorno_do_pix_tardio_pelo_caminho_do_admin():
    """Antes, ``refund_intent_at_gateway`` recusava com ``refund_route_card_machine``."""
    order, booked_ref = _cancelled_with_late_pix("TARDIO-2727-ADMIN")

    result = payment_service.refund_intent_at_gateway(
        booked_ref, amount_q=2200, idempotency_key="admin-tardio", actor="dono",
    )

    assert result.success, result.message
    assert PaymentService.refunded_total(booked_ref) == 2200


def test_atestado_no_balcao_continua_na_maquininha():
    """O Pix atestado no balcão (venda mista) também mora sem gateway, e segue sendo maquininha."""
    order = _paid_pix("ATESTADO-2727")
    asserted = PaymentService.create_intent(
        order.ref, 500, "pix", gateway="", gateway_data={"asserted_at_terminal": True},
    )
    assert order_edit.refund_route(asserted) == order_edit.ROUTE_CARD_MACHINE


# ── Item 3: o sino diz o que fazer, um texto por caso ────────────────────────


def test_sem_por_onde_tentar_daqui_o_sino_segue_com_o_suporte(operador):
    """Pedido pago no dinheiro, cancelado: não há o que pedir ao meio online."""
    order = Order.objects.create(
        ref="DINHEIRO-2727", channel_ref="web", session_key="s-din", status="cancelled", total_q=1500,
        data={"customer": {"name": "Ana"}, "fulfillment_type": "pickup", "payment": {"method": "cash"}},
    )
    payment_service.alert_refund_failed(order, "", 1500, "sem gateway")

    message = _bell(order)
    assert payment_service.REFUND_FAILED_SUPPORT in message
    assert "Tentar o estorno de novo" not in message
    # Aviso aberto sem referência de cobrança: a frase não fica pela metade.
    assert "Referência do pagamento" not in message
    assert "—" not in message
    _detail, line = _refund_line(order, operador)
    assert line.actions == ()
    assert "O suporte já recebeu o aviso" in line.reason


def test_com_o_botao_o_sino_leva_ao_gestor_e_nao_ao_suporte():
    order = _return_refused("SINO-2727")

    message = _bell(order)
    assert message == (
        f"O estorno do pedido {order.ref} (R$ 10,00) não saiu: saldo insuficiente na conta. O dinheiro do "
        "cliente pode estar retido. No Gestor de pedidos, abra o pedido e toque em Tentar o estorno de novo, "
        "com a autorização de um gerente; se o cliente perguntar, diga que o estorno está sendo feito. "
        f"Referência do pagamento: INT-{order.ref}."
    )
    assert "suporte" not in message
    assert "—" not in message


def test_tentativa_sem_resposta_no_gestor_deixa_no_sino_a_frase_do_balcao(client, operador, gerente):
    """O aviso da falta de resposta, pedido no Gestor, não manda conferir "o painel" do gateway."""
    order = _return_refused("MUDO-2727")

    with patch(SIGN, return_value=gerente), patch(ADAPTER, return_value=Gateway("silent")):
        resp = _retry(client, operador, order, manager_approval=APPROVAL)

    assert resp.status_code == 200, resp.content
    assert resp.json()["refund"]["outcome"] == "unconfirmed"
    ambiguous = OperatorAlert.objects.get(order_ref=order.ref, message__contains="ficou sem resposta")
    assert ambiguous.message.split("\n\nDedupe:")[0] == (
        f"O estorno do pedido {order.ref}, tentado de novo no Gestor de pedidos, ficou sem resposta do meio "
        "de pagamento, e pode ter saído. Tente de novo no Gestor em alguns minutos: a tentativa seguinte "
        "confere esta e não devolve duas vezes."
    )
    assert "painel" not in ambiguous.message


# ── A linha do tempo não diz "processado" do que não voltou ──────────────────


def _timeline_labels(order: Order) -> list[str]:
    return [event.label for event in build_operator_order(order).timeline]


def test_devolucao_recusada_nao_grava_estorno_processado(operador):
    """A linha do tempo dizia "Reembolso processado" logo abaixo de "Estorno não saiu"."""
    order = _registered_return(_paid_pix("DEV-2727-NAO-SAIU"))

    result = _process_return(order, "refuse")

    assert result["refund"] == {"success": False, "amount_q": 0, "reason": "gateway_refused"}
    assert not order.events.filter(type="refund_processed").exists()
    assert not any("processado" in label.lower() for label in _timeline_labels(order))
    _detail, line = _refund_line(order, operador)
    assert line.label == "Estorno não saiu"


def test_devolucao_que_o_gateway_aceita_grava_o_estorno_com_o_valor_que_voltou():
    order = _registered_return(_paid_pix("DEV-2727-SAIU"))

    result = _process_return(order, "accept")

    assert result["refund"] == {"success": True, "amount_q": 1000}
    (event,) = order.events.filter(type="refund_processed")
    assert event.payload == {"amount_q": 1000, "success": True}
    assert PaymentService.refunded_total(f"INT-{order.ref}") == 1000


def test_devolucao_sem_resposta_do_gateway_nao_grava_e_fica_com_o_retry():
    order = _registered_return(_paid_pix("DEV-2727-MUDO"))

    result = _process_return(order, "silent")

    assert result["refund"] == {"success": False, "amount_q": 0, "reason": "gateway_unconfirmed"}
    assert not order.events.filter(type="refund_processed").exists()
    assert Directive.objects.filter(topic="payment.refund", payload__order_ref=order.ref, status="queued").exists()


@pytest.mark.parametrize("method", ["cash", "debit"], ids=["gaveta", "maquininha"])
def test_devolucao_de_dinheiro_ou_maquininha_nao_grava_estorno_processado(method):
    """O ``refund`` não estorna gaveta nem maquininha: o dinheiro fica nas listas do PDV."""
    order = Order.objects.create(
        ref=f"DEV-2727-{method.upper()}", channel_ref="web", session_key=f"s-{method}", status="delivered", total_q=3000,
        data={"customer": {"name": "Ana"}, "fulfillment_type": "pickup", "payment": {"method": method}},
    )
    OrderItem.objects.create(
        order=order, line_id=f"{order.ref}-1", sku="PAO", name="Pão", qty=3, unit_price_q=1000, line_total_q=3000,
    )
    intent = PaymentService.settle(order.ref, 3000, method, idempotency_key=f"test:{order.ref}")
    order.data["payment"]["intent_ref"] = intent.ref
    order.save(update_fields=["data", "updated_at"])
    _registered_return(order)

    result = _process_return(order, "accept")

    assert result["refund"] == {"success": False, "amount_q": 0, "reason": "pending_counter_refund"}
    assert not order.events.filter(type="refund_processed").exists()
    assert PaymentService.refunded_total(intent.ref) == 0


def test_a_devolucao_recusada_encerra_a_etapa_sem_retentar_nem_travar():
    """O handler não retenta a devolução por um estorno que já tem dono (sino e Gestor)."""
    from shopman.shop.handlers.returns import ReturnHandler

    order = _registered_return(_paid_pix("DEV-2727-HANDLER"))
    record = order.data["returns"][0]
    task = Directive.objects.create(
        topic="return.process", status="running", attempts=1,
        payload={"order_ref": order.ref, "items": record["items"], "refund_total_q": 1000, "return_index": 0},
    )

    with patch(ADAPTER, return_value=Gateway("refuse")):
        ReturnHandler().handle(message=task, ctx={})

    order.refresh_from_db()
    assert order.data["returns"][0]["refund_processed"] is True
    assert not order.events.filter(type="refund_processed").exists()
    assert not OperatorAlert.objects.filter(type="lifecycle_phase_stuck", order_ref=order.ref).exists()
    assert OperatorAlert.objects.filter(type="payment_refund_failed", order_ref=order.ref, resolved_at__isnull=True)


def test_tentar_de_novo_com_sucesso_nao_grava_um_segundo_estorno_processado(client, operador, gerente):
    order = _return_refused("DEV-2727-UM-SO")

    with patch(SIGN, return_value=gerente), patch(ADAPTER, return_value=Gateway()):
        resp = _retry(client, operador, order, manager_approval=APPROVAL)

    assert resp.status_code == 200, resp.content
    assert resp.json()["refund"]["outcome"] == "refunded"
    assert not order.events.filter(type="refund_processed").exists()
    timeline = {event["event_type"]: event for event in resp.json()["order"]["timeline"]}
    assert timeline["payment.refund_retry"]["detail"].endswith("o meio de pagamento confirmou")
