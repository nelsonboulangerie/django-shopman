"""Tentar o estorno de novo no Gestor (WP-G13, EXCELENCIA-GESTOR P1-15, decisão 3 do dono).

O estorno do cancelado que falhou deixava o pedido em "Estorno não saiu" esperando o
suporte. Agora a linha da faixa tem o gesto, com a assinatura de um Gerente. Esta suíte
prende:

- a rota só existe para o dinheiro do cancelado em "Estorno não saiu";
- pede a permissão de gerenciar pedidos e o PIN de um Gerente, e sem ele nada é gravado;
- a chave é por tentativa: a mesma tentativa duas vezes fala com o gateway uma vez só, e
  uma tentativa nova, depois de outra recusada, leva outra chave;
- a tentativa sem resposta do gateway repete a chave na vez seguinte;
- no "não retirado", o que volta nunca passa do teto (o capturado menos o retido);
- a recusa do gateway fica escrita na linha, e a linha do tempo diz quem tentou e quem
  autorizou.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.contrib.auth.models import Permission
from django.test import override_settings
from django.urls import reverse
from shopman.orderman.models import Directive, IdempotencyKey, Order, OrderItem
from shopman.payman import PaymentService
from shopman.payman.models import PaymentTransaction

from shopman.backstage.models import OperatorAlert
from shopman.backstage.projections.order_queue import build_operator_order
from shopman.backstage.services import refund_retry
from shopman.shop.adapters import payment_mock
from shopman.shop.models import Shop
from shopman.shop.services import payment as payment_service

pytestmark = [
    pytest.mark.django_db,
    pytest.mark.channels("web"),
    pytest.mark.usefixtures("_mock_gateway"),
]

SIGN = "shopman.backstage.api.operations.pos_tabs_service.validate_manager_override"
ADAPTER = "shopman.shop.services.payment._adapter_for_persisted_intent"
APPROVAL = {"username": "gerente", "pin": "SYNTHETIC-NOT-A-PIN"}


@pytest.fixture
def _mock_gateway():
    Shop.objects.create(name="Padaria do estorno")
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
    user = django_user_model.objects.create_user(username="caixa-estorno", is_staff=True)
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
        self.calls.append({"intent_ref": intent_ref, "amount_q": amount_q, "reason": reason, "key": idempotency_key})
        if self.mode == "refuse":
            return SimpleNamespace(success=False, message="saldo insuficiente na conta", error_code="E_DECLINED")
        if self.mode == "silent":
            raise TimeoutError("gateway mudo")
        return payment_mock.refund(intent_ref, amount_q=amount_q, reason=reason, idempotency_key=idempotency_key)


def _cancelled_pix(ref: str, *, total_q: int = 2200, status: str = "cancelled", **data) -> Order:
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
        order=order, line_id=f"{ref}-1", sku="PAO", name="Pão", qty=1, unit_price_q=total_q, line_total_q=total_q,
    )
    PaymentService.create_intent(order.ref, total_q, "pix", gateway="mock", ref=f"INT-{ref}")
    PaymentService.authorize(f"INT-{ref}", gateway_id=f"gw-{ref}")
    PaymentService.capture(f"INT-{ref}")
    return order


def _failed(ref: str, **kwargs) -> Order:
    """Pix capturado, pedido cancelado e o estorno recusado: a linha "Estorno não saiu"."""
    order = _cancelled_pix(ref, **kwargs)
    payment_service.alert_refund_failed(order, f"INT-{ref}", order.total_q, "recusado pelo gateway")
    return order


def _retry(client, user, order, *, key=None, base=None, **body):
    payload = {"expected_actor_id": user.pk, "base_revision": base or refund_retry.revision(order), **body}
    return client.post(
        reverse("api-backstage-order-refund-retry", args=[order.ref]), payload,
        content_type="application/json", HTTP_IDEMPOTENCY_KEY=key or str(uuid.uuid4()),
    )


def _attempts(order: Order) -> list:
    return list(order.events.filter(type=refund_retry.EVENT_TYPE).order_by("seq"))


def _refunds(ref: str):
    return PaymentTransaction.objects.filter(intent__ref=f"INT-{ref}", type="refund")


def _refund_line(order: Order, user=None):
    detail = build_operator_order(order, user=user)
    return detail, {item.key: item for item in detail.pending}.get("refund")


# ── Quem pode, e com que assinatura ──────────────────────────────────────────


def test_sem_a_permissao_de_gerenciar_pedidos_a_rota_recusa(client, django_user_model):
    order = _failed("G13-PERM")
    user = django_user_model.objects.create_user(username="so-expede", is_staff=True)
    client.force_login(user)

    resp = _retry(client, user, order, manager_approval=APPROVAL)

    assert resp.status_code == 403, resp.content
    assert _attempts(order) == []
    assert not _refunds("G13-PERM").exists()


def test_pede_o_gerente_e_nao_grava_nada_sem_a_assinatura(client, operador):
    order = _failed("G13-SEM-PIN")
    key = str(uuid.uuid4())

    resp = _retry(client, operador, order, key=key)

    assert resp.status_code == 422, resp.content
    body = resp.json()
    assert body["error"]["code"] == "manager_approval_required"
    assert body["detail"] == "Tentar o estorno de novo pede a autorização de um gerente."
    assert (body["outcome"], body["intention"]) == ("not_applied", key)
    assert _attempts(order) == []
    assert not _refunds("G13-SEM-PIN").exists()
    assert not IdempotencyKey.objects.filter(key=key).exists()


def test_pin_errado_e_recusado_pelo_validador_de_verdade_e_nada_sai(client, operador):
    order = _failed("G13-PIN-ERRADO")
    gateway = Gateway()

    with patch(ADAPTER, return_value=gateway):
        resp = _retry(client, operador, order, manager_approval={"username": "ninguem", "pin": "0000"})

    assert resp.status_code == 422, resp.content
    assert resp.json()["error"]["code"] == "manager_approval_invalid"
    assert gateway.calls == []
    assert _attempts(order) == []


# ── O estorno que sai ────────────────────────────────────────────────────────


def test_assinado_o_estorno_sai_e_o_pedido_diz_quem_tentou_e_quem_autorizou(client, operador, gerente):
    order = _failed("G13-SAI")
    key = str(uuid.uuid4())
    gateway = Gateway()

    with patch(SIGN, return_value=gerente) as signature, patch(ADAPTER, return_value=gateway):
        resp = _retry(client, operador, order, key=key, manager_approval=APPROVAL)

    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert body["outcome"] == "applied"
    assert body["refund"] == {"outcome": "refunded", "amount_q": 2200, "refunded_q": 2200, "message": ""}
    assert signature.call_args.kwargs["action"] == "order_refund_retry"
    assert signature.call_args.kwargs["message"] == "Tentar o estorno de novo pede a autorização de um gerente."

    # O dinheiro voltou pelo gateway, com o motivo dizendo de onde o pedido saiu.
    (call,) = gateway.calls
    assert (call["intent_ref"], call["amount_q"]) == ("INT-G13-SAI", 2200)
    assert call["key"] == refund_retry.fresh_gateway_key("G13-SAI", "INT-G13-SAI", key)
    assert call["key"].startswith("order-refund-retry:G13-SAI:INT-G13-SAI:") and len(call["key"]) < 100
    assert call["reason"] == "Estorno no Gestor por caixa-estorno, autorizado por joyce"
    assert PaymentService.refunded_total("INT-G13-SAI") == 2200

    # A linha do tempo: quem tentou é o autor, quem autorizou está no evento.
    (attempt,) = _attempts(order)
    assert attempt.actor == "caixa-estorno"
    assert attempt.payload["approved_by"] == "joyce"
    assert (attempt.payload["outcome"], attempt.payload["amount_q"]) == ("refunded", 2200)
    refunded = order.events.get(type="payment.refunded")
    assert refunded.payload == {"method": "pix", "amount_q": 2200, "intent_ref": "INT-G13-SAI"}

    # A tela recebe o pedido já relido: "Estornado", sem a linha e sem o aviso do sino.
    assert body["order"]["cancelled_money"]["state"] == "refunded"
    assert body["order"]["payment_status_label"] == "Estornado"
    assert not any(item["key"] == "refund" for item in body["order"]["pending"])
    assert not OperatorAlert.objects.filter(order_ref=order.ref, resolved_at__isnull=True).exists()
    timeline = {event["event_type"]: event for event in body["order"]["timeline"]}
    assert timeline["payment.refund_retry"]["label"] == "Estorno tentado de novo"
    assert timeline["payment.refund_retry"]["detail"] == (
        "Pix · R$ 22,00 · autorizado por Joyce · o meio de pagamento confirmou"
    )
    assert "SYNTHETIC-NOT-A-PIN" not in str(IdempotencyKey.objects.get(key=key).response_body)


def test_o_gerente_que_opera_assina_o_proprio_gesto(client, operador):
    order = _failed("G13-PROPRIO")
    gateway = Gateway()

    with patch(SIGN, return_value=operador), patch(ADAPTER, return_value=gateway):
        resp = _retry(client, operador, order, manager_approval=APPROVAL)

    assert resp.status_code == 200, resp.content
    assert gateway.calls[0]["reason"] == "Estorno no Gestor por caixa-estorno"


def test_a_mesma_tentativa_duas_vezes_fala_com_o_gateway_uma_vez_so(client, operador, gerente):
    order = _failed("G13-DUPLO")
    base = refund_retry.revision(order)
    key = str(uuid.uuid4())
    gateway = Gateway()

    with patch(SIGN, return_value=gerente), patch(ADAPTER, return_value=gateway):
        first = _retry(client, operador, order, key=key, base=base, manager_approval=APPROVAL)
        second = _retry(client, operador, order, key=key, base=base, manager_approval=APPROVAL)

    assert (first.status_code, second.status_code) == (200, 200)
    assert first.json()["replayed"] is False
    assert second.json()["replayed"] is True
    assert second.json()["refund"] == first.json()["refund"]
    assert len(gateway.calls) == 1
    assert _refunds("G13-DUPLO").count() == 1
    assert len(_attempts(order)) == 1


# ── Só em "Estorno não saiu" ─────────────────────────────────────────────────


def _alive(ref):
    order = _cancelled_pix(ref, status="completed")
    payment_service.alert_refund_failed(order, f"INT-{ref}", order.total_q, "recusado pelo gateway")
    return order


def _already_refunded(ref):
    order = _failed(ref)
    PaymentService.refund(f"INT-{ref}", reason="order_cancelled")
    return order


def _in_flight(ref):
    order = _failed(ref)
    Directive.objects.create(topic="payment.refund", status="queued", payload={"order_ref": order.ref})
    return order


@pytest.mark.parametrize(
    ("build", "expected"),
    [
        (_alive, "Este pedido não tem estorno que falhou para tentar de novo."),
        (_cancelled_pix, "O estorno deste pedido foi pedido e não falhou: é só esperar a confirmação."),
        (_already_refunded, "O estorno deste pedido já saiu."),
        (_in_flight, "O sistema ainda está tentando este estorno sozinho. Espere ele terminar para tentar de novo."),
    ],
    ids=["pedido-vivo", "estorno-pedido", "estornado", "sistema-tentando"],
)
def test_fora_do_estorno_nao_saiu_a_rota_recusa_com_a_frase_do_motivo(client, operador, gerente, build, expected):
    order = build("G13-ESTADO")
    gateway = Gateway()

    with patch(SIGN, return_value=gerente), patch(ADAPTER, return_value=gateway):
        resp = _retry(client, operador, order, manager_approval=APPROVAL)

    assert resp.status_code == 409, resp.content
    body = resp.json()
    assert body["detail"] == expected
    assert body["error"]["code"] == "refund_retry_not_allowed"
    assert body["outcome"] == "not_applied"
    assert gateway.calls == []
    assert _attempts(order) == []


def test_pedido_que_nao_existe_e_404(client, operador):
    resp = client.post(reverse("api-backstage-order-refund-retry", args=["NAO-EXISTE"]), {}, content_type="application/json")
    assert resp.status_code == 404


def test_a_tela_velha_e_recusada_e_o_gateway_nao_e_chamado(client, operador, gerente):
    order = _failed("G13-VELHA")
    gateway = Gateway()

    with patch(SIGN, return_value=gerente), patch(ADAPTER, return_value=gateway):
        resp = _retry(client, operador, order, base="base-de-outra-leitura", manager_approval=APPROVAL)

    assert resp.status_code == 409, resp.content
    assert resp.json()["detail"] == "O estorno deste pedido mudou depois que você abriu a tela. Confira e tente de novo."
    assert gateway.calls == []
    assert _attempts(order) == []


# ── O gateway recusa de novo ─────────────────────────────────────────────────


def test_o_gateway_recusa_de_novo_a_resposta_diz_o_que_ele_disse_e_a_linha_continua(client, operador, gerente):
    order = _failed("G13-RECUSA")
    gateway = Gateway("refuse")
    first_key = str(uuid.uuid4())

    with patch(SIGN, return_value=gerente), patch(ADAPTER, return_value=gateway):
        resp = _retry(client, operador, order, key=first_key, manager_approval=APPROVAL)

    assert resp.status_code == 200, resp.content
    body = resp.json()
    answer = (
        "O estorno foi recusado (gateway de teste), e nada foi registrado aqui. "
        "Resposta (gateway de teste): saldo insuficiente na conta."
    )
    assert body["refund"] == {"outcome": "refused", "amount_q": 2200, "refunded_q": 0, "message": answer}
    assert PaymentService.refunded_total("INT-G13-RECUSA") == 0
    assert not order.events.filter(type="payment.refunded").exists()
    assert OperatorAlert.objects.filter(order_ref=order.ref, resolved_at__isnull=True).exists()

    # A tentativa ficou no pedido, com quem autorizou e o que o gateway respondeu.
    (attempt,) = _attempts(order)
    assert (attempt.payload["outcome"], attempt.payload["approved_by"], attempt.payload["message"]) == (
        "refused", "joyce", answer,
    )

    # A linha continua em "Estorno não saiu", com a falha escrita nela e o gesto de pé.
    assert body["order"]["cancelled_money"]["state"] == "refund_failed"
    line = next(item for item in body["order"]["pending"] if item["key"] == "refund")
    assert (line["tone"], line["label"]) == ("error", "Estorno não saiu")
    assert "suporte" not in line["reason"]
    assert line["failure"].startswith("Última tentativa, em ")
    assert line["failure"].endswith(f": {answer}")
    assert [(action["ref"], action["enabled"]) for action in line["actions"]] == [("refund-retry", True)]
    timeline = {event["event_type"]: event for event in body["order"]["timeline"]}
    assert timeline["payment.refund_retry"]["detail"] == f"Pix · R$ 22,00 · autorizado por Joyce · não saiu: {answer}"

    # Uma tentativa NOVA, depois da recusa, é permitida e leva outra chave ao gateway.
    order.refresh_from_db()
    gateway.mode = "accept"
    second_key = str(uuid.uuid4())
    with patch(SIGN, return_value=gerente), patch(ADAPTER, return_value=gateway):
        again = _retry(client, operador, order, key=second_key, manager_approval=APPROVAL)

    assert again.status_code == 200, again.content
    assert again.json()["refund"]["outcome"] == "refunded"
    assert [call["key"] for call in gateway.calls] == [
        refund_retry.fresh_gateway_key("G13-RECUSA", "INT-G13-RECUSA", first_key),
        refund_retry.fresh_gateway_key("G13-RECUSA", "INT-G13-RECUSA", second_key),
    ]
    assert gateway.calls[0]["key"] != gateway.calls[1]["key"]
    assert PaymentService.refunded_total("INT-G13-RECUSA") == 2200
    assert again.json()["order"]["cancelled_money"]["state"] == "refunded"


def test_cobranca_sem_caminho_ate_o_gateway_recusa_com_a_frase_e_depois_sai(client, operador, gerente):
    """Sem dublê: a cobrança de um gateway que a configuração não conhece é recusada antes
    de qualquer chamada, e volta a estornar quando o caminho existe (o simulador)."""
    from shopman.payman.models import PaymentIntent

    order = _failed("G13-SEM-ROTA")
    PaymentIntent.objects.filter(ref="INT-G13-SEM-ROTA").update(gateway="gateway-desconhecido")

    with patch(SIGN, return_value=gerente):
        resp = _retry(client, operador, order, manager_approval=APPROVAL)

    assert resp.status_code == 200, resp.content
    refund = resp.json()["refund"]
    assert refund["outcome"] == "refused"
    assert refund["message"].startswith("Não há como chegar ao gateway desta cobrança com a configuração de hoje")
    assert PaymentService.refunded_total("INT-G13-SEM-ROTA") == 0
    line = next(item for item in resp.json()["order"]["pending"] if item["key"] == "refund")
    assert "Não há como chegar ao gateway desta cobrança" in line["failure"]

    PaymentIntent.objects.filter(ref="INT-G13-SEM-ROTA").update(gateway="mock")
    order.refresh_from_db()
    with patch(SIGN, return_value=gerente):
        again = _retry(client, operador, order, manager_approval=APPROVAL)

    assert again.status_code == 200, again.content
    assert again.json()["refund"]["outcome"] == "refunded"
    assert PaymentService.refunded_total("INT-G13-SEM-ROTA") == 2200
    assert again.json()["order"]["cancelled_money"]["state"] == "refunded"


def test_a_base_lida_antes_da_tentativa_recusada_nao_serve_para_a_seguinte(client, operador, gerente):
    order = _failed("G13-BASE")
    base = refund_retry.revision(order)
    gateway = Gateway("refuse")

    with patch(SIGN, return_value=gerente), patch(ADAPTER, return_value=gateway):
        _retry(client, operador, order, base=base, manager_approval=APPROVAL)
        stale = _retry(client, operador, order, base=base, manager_approval=APPROVAL)

    assert stale.status_code == 409, stale.content
    assert len(gateway.calls) == 1


def test_tentativa_sem_resposta_repete_a_chave_na_vez_seguinte(client, operador, gerente):
    """O estorno pode ter saído: só a mesma chave faz o gateway devolver a MESMA devolução."""
    order = _failed("G13-MUDO")
    gateway = Gateway("silent")
    first_key = str(uuid.uuid4())

    with patch(SIGN, return_value=gerente), patch(ADAPTER, return_value=gateway):
        resp = _retry(client, operador, order, key=first_key, manager_approval=APPROVAL)

    assert resp.status_code == 200, resp.content
    refund = resp.json()["refund"]
    assert refund["outcome"] == "unconfirmed"
    assert refund["message"] == (
        "O meio de pagamento não respondeu, e não dá para saber se o estorno saiu. Tente de novo em alguns minutos."
    )
    assert resp.json()["order"]["cancelled_money"]["state"] == "refund_failed"

    order.refresh_from_db()
    gateway.mode = "accept"
    with patch(SIGN, return_value=gerente), patch(ADAPTER, return_value=gateway):
        again = _retry(client, operador, order, manager_approval=APPROVAL)

    assert again.status_code == 200, again.content
    assert again.json()["refund"]["outcome"] == "refunded"
    assert [call["key"] for call in gateway.calls] == [
        refund_retry.fresh_gateway_key("G13-MUDO", "INT-G13-MUDO", first_key),
    ] * 2
    assert _refunds("G13-MUDO").count() == 1


def test_dinheiro_que_saiu_sem_registro_trava_a_tentativa_seguinte(client, operador, gerente):
    order = _failed("G13-LIVRO")

    class Unrecorded:
        calls = 0

        def refund(self, intent_ref, **kwargs):
            self.calls += 1
            return SimpleNamespace(success=True, transaction_id="dev-sem-registro", amount_q=kwargs["amount_q"])

    gateway = Unrecorded()
    with patch(SIGN, return_value=gerente), patch(ADAPTER, return_value=gateway):
        resp = _retry(client, operador, order, manager_approval=APPROVAL)
        order.refresh_from_db()
        again = _retry(client, operador, order, manager_approval=APPROVAL)

    assert resp.status_code == 200, resp.content
    assert resp.json()["refund"]["outcome"] == "unrecorded"
    assert again.status_code == 409, again.content
    assert again.json()["detail"] == refund_retry.UNRECORDED_REASON
    assert gateway.calls == 1
    line = next(item for item in resp.json()["order"]["pending"] if item["key"] == "refund")
    assert line["actions"] == []
    assert refund_retry.UNRECORDED_REASON in line["reason"]


# ── O teto do "não retirado" ─────────────────────────────────────────────────


def test_no_nao_retirado_o_estorno_de_novo_nunca_passa_do_teto(client, operador, gerente):
    """Pago R$ 48,70, a loja fica com R$ 30,00: voltam R$ 18,70, e nem um centavo a mais."""
    order = _failed(
        "G13-TETO", total_q=4870,
        cancellation_reason_key="not_picked_up",
        no_show={"paid_q": 4870, "refund_q": 1870, "retained_q": 3000, "approved_by": "joyce", "lines": []},
    )
    gateway = Gateway()
    assert refund_retry.plan(order).amount_q == 1870

    with patch(SIGN, return_value=gerente), patch(ADAPTER, return_value=gateway):
        resp = _retry(client, operador, order, manager_approval=APPROVAL)

    assert resp.status_code == 200, resp.content
    assert resp.json()["refund"] == {"outcome": "refunded", "amount_q": 1870, "refunded_q": 1870, "message": ""}
    assert [call["amount_q"] for call in gateway.calls] == [1870]
    assert PaymentService.refunded_total("INT-G13-TETO") == 1870
    assert payment_service.captured_balance_q(order) == 3000

    # O que ficou com a loja não se pede de novo: a rota já não existe para este pedido.
    order.refresh_from_db()
    with patch(SIGN, return_value=gerente), patch(ADAPTER, return_value=gateway):
        again = _retry(client, operador, order, manager_approval=APPROVAL)
    assert again.status_code == 409, again.content
    assert len(gateway.calls) == 1
    assert PaymentService.refunded_total("INT-G13-TETO") == 1870


def test_teto_com_parte_ja_devolvida_pede_so_o_que_falta(client, operador, gerente):
    order = _failed(
        "G13-RESTO", total_q=4870,
        cancellation_reason_key="not_picked_up",
        no_show={"paid_q": 4870, "refund_q": 1870, "retained_q": 3000, "approved_by": "joyce", "lines": []},
    )
    PaymentService.refund("INT-G13-RESTO", amount_q=1000, reason="order_cancelled", gateway_id="parte-que-saiu")
    gateway = Gateway()

    with patch(SIGN, return_value=gerente), patch(ADAPTER, return_value=gateway):
        resp = _retry(client, operador, order, manager_approval=APPROVAL)

    assert resp.status_code == 200, resp.content
    assert [call["amount_q"] for call in gateway.calls] == [870]
    assert PaymentService.refunded_total("INT-G13-RESTO") == 1870


# ── A faixa do detalhe ───────────────────────────────────────────────────────


def test_a_linha_do_estorno_que_nao_saiu_ganha_o_gesto_e_diz_o_valor_e_o_que_ele_faz(operador):
    order = _failed("G13-LINHA")

    detail, line = _refund_line(order, operador)

    assert (line.tone, line.label) == ("error", "Estorno não saiu")
    assert line.reason == (
        "A devolução de R$ 22,00 não chegou ao cliente. Tentar de novo pede esse estorno outra vez "
        "ao Pix do cliente, com a autorização de um gerente."
    )
    assert "suporte" not in line.reason
    (action,) = line.actions
    assert (action.ref, action.label, action.enabled, action.reason) == (
        "refund-retry", "Tentar o estorno de novo", True, "",
    )
    # A ação da linha é a MESMA do detalhe, com a base e a assinatura que a rota confere.
    contract = next(item for item in detail.actions if item.ref == "refund-retry")
    assert contract.payload_schema == {"base_revision": refund_retry.revision(order), "expected_actor_id": operador.pk}
    assert contract.confirmation == {"required": True, "manager_approval": True}
    assert (contract.method, contract.idempotency) == ("POST", "required")
    assert line.failure == ""
    assert "—" not in line.reason


def test_sem_pessoa_com_permissao_o_gesto_aparece_desligado_com_o_motivo():
    order = _failed("G13-SEM-PESSOA")

    _detail, line = _refund_line(order)

    (action,) = line.actions
    assert action.enabled is False
    assert action.reason == "Identifique uma pessoa com permissão para gerenciar pedidos."


def test_estorno_pedido_e_estornado_nao_ganham_o_gesto(operador):
    requested = _cancelled_pix("G13-PEDIDO")
    detail, line = _refund_line(requested, operador)
    assert line.actions == ()
    assert not any(action.ref == "refund-retry" for action in detail.actions)

    refunded = _already_refunded("G13-ESTORNADO")
    detail, line = _refund_line(refunded, operador)
    assert line is None
    assert not any(action.ref == "refund-retry" for action in detail.actions)


def test_estorno_que_falhou_fora_do_cancelado_segue_com_o_suporte(operador):
    """Devolução e encomenda editada: sem o valor certo a pedir de novo, o gesto não aparece."""
    order = _alive("G13-VIVO")

    detail, line = _refund_line(order, operador)

    assert line.label == "Estorno não saiu"
    assert line.actions == ()
    assert "O suporte já recebeu o aviso" in line.reason
    assert not any(action.ref == "refund-retry" for action in detail.actions)
