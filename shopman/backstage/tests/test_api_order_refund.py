"""Estornar UM pedido no Gestor (#2727, item 5; dono, 21/11/2026).

A exceção financeira do Gerente: ``backstage.refund_single_order``. A trava de que
ele não lista nem soma cobranças é ``shop/tests/test_gerente_sem_permissao_financeira.py``;
esta suíte prende o gesto:

- a porta só aparece a quem tem a permissão, e só no pedido com cobrança online paga;
- a segunda confirmação (``confirm``) é obrigatória, como no diálogo do Admin;
- parcial vale, até o disponível; em branco, o disponível inteiro;
- o dinheiro sai pelo mesmo caminho do Admin (``payment.refund_intent_at_gateway``);
- a mesma intenção duas vezes fala com o gateway uma vez só;
- a tentativa sem resposta faz a seguinte, com o mesmo valor, repetir a chave;
- a tela velha é recusada, e a linha do tempo diz quem estornou e quanto.
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

from shopman.backstage.projections.order_queue import build_operator_order
from shopman.backstage.services import order_refund
from shopman.shop.adapters import payment_mock
from shopman.shop.models import Shop

pytestmark = [
    pytest.mark.django_db,
    pytest.mark.channels("web"),
    pytest.mark.usefixtures("_mock_gateway"),
]

ADAPTER = "shopman.shop.services.payment._adapter_for_persisted_intent"


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


def _user(django_user_model, username: str, *perms: str):
    user = django_user_model.objects.create_user(username=username, is_staff=True)
    for perm in perms:
        app_label, codename = perm.split(".")
        user.user_permissions.add(Permission.objects.get(content_type__app_label=app_label, codename=codename))
    return django_user_model.objects.get(pk=user.pk)


@pytest.fixture
def gerente(client, django_user_model):
    user = _user(django_user_model, "joyce", "shop.manage_orders", order_refund.PERMISSION)
    client.force_login(user)
    return user


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


def _paid(ref: str, *, total_q: int = 3000, method: str = "pix", status: str = "completed") -> Order:
    order = Order.objects.create(
        ref=ref, channel_ref="web", session_key=f"s-{ref}", status=status, total_q=total_q,
        data={
            "customer": {"name": f"Cliente {ref}"},
            "fulfillment_type": "pickup",
            "payment": {"method": method, "intent_ref": f"INT-{ref}"},
        },
    )
    OrderItem.objects.create(
        order=order, line_id=f"{ref}-1", sku="PAO", name="Pão", qty=1, unit_price_q=total_q, line_total_q=total_q,
    )
    PaymentService.create_intent(order.ref, total_q, method, gateway="mock" if method != "cash" else "", ref=f"INT-{ref}")
    PaymentService.authorize(f"INT-{ref}", gateway_id=f"gw-{ref}")
    PaymentService.capture(f"INT-{ref}")
    return order


def _refund(client, user, order, *, key=None, base=None, **body):
    payload = {
        "expected_actor_id": user.pk,
        "base_revision": base or order_refund.revision(order, order_refund.plan(order)),
        "confirm": True,
        **body,
    }
    return client.post(
        reverse("api-backstage-order-refund", args=[order.ref]), payload,
        content_type="application/json", HTTP_IDEMPOTENCY_KEY=key or str(uuid.uuid4()),
    )


def _attempts(order: Order) -> list:
    return list(order.events.filter(type=order_refund.EVENT_TYPE).order_by("seq"))


def _refunds(ref: str):
    return PaymentTransaction.objects.filter(intent__ref=f"INT-{ref}", type="refund")


def _action(order: Order, user):
    detail = build_operator_order(order, user=user)
    return {action.ref: action for action in detail.actions}.get(order_refund.ACTION_REF)


# ── A porta ──────────────────────────────────────────────────────────────────


def test_a_permissao_existe_no_modelo():
    assert Permission.objects.filter(content_type__app_label="backstage", codename="refund_single_order").exists()


def test_a_porta_so_aparece_a_quem_tem_a_permissao(gerente, django_user_model):
    order = _paid("EST-PORTA")
    caixa = _user(django_user_model, "caixa", "shop.manage_orders")

    action = _action(order, gerente)

    assert action is not None and action.enabled, action
    assert action.label == "Estornar"
    assert action.payload_schema["base_revision"] == order_refund.revision(order, order_refund.plan(order))
    assert _action(order, caixa) is None


def test_sem_cobranca_online_paga_nao_ha_porta(gerente):
    order = _paid("EST-DINHEIRO", method="cash")
    assert _action(order, gerente) is None


def test_estornado_inteiro_a_porta_fica_travada_dizendo_por_que(gerente):
    order = _paid("EST-INTEIRO")
    PaymentService.refund(f"INT-{order.ref}", reason="teste")

    action = _action(order, gerente)

    assert action is not None and not action.enabled
    assert action.reason == "O valor desta cobrança já voltou inteiro ao cliente."


def test_com_o_estorno_automatico_em_curso_a_porta_fica_travada(gerente):
    order = _paid("EST-CURSO")
    Directive.objects.create(topic="payment.refund", status="queued", payload={"order_ref": order.ref})

    action = _action(order, gerente)

    assert action is not None and not action.enabled
    assert action.reason.startswith("O sistema ainda está tentando este estorno sozinho.")


def test_a_previa_mostra_o_pago_o_que_voltou_e_o_disponivel(client, gerente):
    order = _paid("EST-PREVIA", total_q=3000)
    PaymentService.refund(f"INT-{order.ref}", amount_q=500, reason="teste")

    resp = client.get(reverse("api-backstage-order-refund-preview", args=[order.ref]))

    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert (body["paid_display"], body["returned_display"], body["available_display"]) == (
        "R$ 30,00", "R$ 5,00", "R$ 25,00",
    )
    assert (body["available_q"], body["partial_allowed"], body["blocked"]) == (2500, True, False)
    assert body["action"]["ref"] == "refund" and body["action"]["enabled"] is True


# ── O estorno ────────────────────────────────────────────────────────────────


def test_sem_a_segunda_confirmacao_nada_sai(client, gerente):
    order = _paid("EST-SEM-MARCA")
    gateway = Gateway()

    with patch(ADAPTER, return_value=gateway):
        resp = _refund(client, gerente, order, confirm=False)

    assert resp.status_code == 400, resp.content
    assert resp.json()["field"] == "confirm"
    assert gateway.calls == []
    assert _attempts(order) == []


def test_parcial_sai_pelo_caminho_do_admin_e_a_linha_do_tempo_diz_quanto(client, gerente):
    order = _paid("EST-PARCIAL", total_q=3000)
    key = str(uuid.uuid4())
    gateway = Gateway()

    with patch(ADAPTER, return_value=gateway):
        resp = _refund(client, gerente, order, key=key, amount_q=1200)

    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert body["outcome"] == "applied"
    assert body["refund"] == {"outcome": "refunded", "amount_q": 1200, "refunded_q": 1200, "available_q": 1800, "message": ""}
    assert "order" not in body, "a resposta é o recibo da cobrança; o pedido se relê pelo detalhe"
    (call,) = gateway.calls
    assert (call["intent_ref"], call["amount_q"]) == ("INT-EST-PARCIAL", 1200)
    assert call["key"] == order_refund.fresh_gateway_key(order.ref, "INT-EST-PARCIAL", key)
    assert call["reason"] == "Estorno no Gestor por joyce"
    assert PaymentService.refunded_total("INT-EST-PARCIAL") == 1200

    (attempt,) = _attempts(order)
    assert attempt.actor == "joyce"
    assert (attempt.payload["outcome"], attempt.payload["amount_q"]) == ("refunded", 1200)
    timeline = {event.event_type: event for event in build_operator_order(order, user=gerente).timeline}
    assert timeline["payment.order_refund"].label == "Estorno pedido no Gestor"
    assert timeline["payment.order_refund"].detail == "Pix · R$ 12,00 · o meio de pagamento confirmou"


def test_em_branco_estorna_o_disponivel_inteiro(client, gerente):
    order = _paid("EST-TUDO", total_q=3000)
    gateway = Gateway()

    with patch(ADAPTER, return_value=gateway):
        resp = _refund(client, gerente, order)

    assert resp.status_code == 200, resp.content
    assert resp.json()["refund"]["refunded_q"] == 3000
    assert PaymentService.refunded_total("INT-EST-TUDO") == 3000
    assert not _action(order, gerente).enabled


def test_acima_do_disponivel_e_recusado_e_nada_sai(client, gerente):
    order = _paid("EST-ACIMA", total_q=3000)
    gateway = Gateway()

    with patch(ADAPTER, return_value=gateway):
        resp = _refund(client, gerente, order, amount_q=3001)

    assert resp.status_code == 409, resp.content
    assert resp.json()["detail"] == "Valor acima do disponível (R$ 30,00)."
    assert resp.json()["outcome"] == "not_applied"
    assert gateway.calls == []


@pytest.mark.parametrize("amount", ["12,00", -5, 0, True])
def test_valor_que_nao_e_centavos_inteiros_e_recusado(client, gerente, amount):
    order = _paid("EST-VALOR")

    resp = _refund(client, gerente, order, amount_q=amount)

    assert resp.status_code == 400, resp.content
    assert resp.json()["field"] == "amount_q"


def test_a_mesma_intencao_duas_vezes_fala_com_o_gateway_uma_vez_so(client, gerente):
    order = _paid("EST-DUPLO")
    base = order_refund.revision(order, order_refund.plan(order))
    key = str(uuid.uuid4())
    gateway = Gateway()

    with patch(ADAPTER, return_value=gateway):
        first = _refund(client, gerente, order, key=key, base=base, amount_q=1000)
        second = _refund(client, gerente, order, key=key, base=base, amount_q=1000)

    assert (first.status_code, second.status_code) == (200, 200)
    assert second.json()["replayed"] is True
    assert len(gateway.calls) == 1
    assert _refunds("EST-DUPLO").count() == 1


def test_sem_resposta_do_gateway_a_tentativa_seguinte_repete_a_chave(client, gerente):
    order = _paid("EST-MUDO")
    silent = Gateway("silent")

    with patch(ADAPTER, return_value=silent):
        first = _refund(client, gerente, order, amount_q=1000)
    order.refresh_from_db()
    accept = Gateway()
    with patch(ADAPTER, return_value=accept):
        second = _refund(client, gerente, order, amount_q=1000)

    assert first.status_code == 200, first.content
    assert first.json()["refund"]["outcome"] == "unconfirmed"
    assert second.json()["refund"]["outcome"] == "refunded"
    assert accept.calls[0]["key"] == silent.calls[0]["key"]


def test_a_recusa_do_gateway_fica_escrita_com_a_frase_do_balcao(client, gerente):
    order = _paid("EST-RECUSA")

    with patch(ADAPTER, return_value=Gateway("refuse")):
        resp = _refund(client, gerente, order)

    assert resp.status_code == 200, resp.content
    refund = resp.json()["refund"]
    assert (refund["outcome"], refund["refunded_q"]) == ("refused", 0)
    assert refund["message"] == "O Pix não aceitou o estorno. Nada foi devolvido ao cliente. Chame o suporte."
    assert _attempts(order)[0].payload["gateway_message"]
    assert not _refunds("EST-RECUSA").exists()


def test_a_tela_velha_e_recusada_e_o_gateway_nao_e_chamado(client, gerente):
    order = _paid("EST-VELHA")
    gateway = Gateway()

    with patch(ADAPTER, return_value=gateway):
        resp = _refund(client, gerente, order, base="base-de-outra-leitura")

    assert resp.status_code == 409, resp.content
    assert resp.json()["detail"] == order_refund.STALE_MESSAGE
    assert gateway.calls == []


def test_quem_so_gerencia_pedidos_recebe_403(client, django_user_model):
    order = _paid("EST-403")
    caixa = _user(django_user_model, "caixa-403", "shop.manage_orders")
    client.force_login(caixa)

    resp = _refund(client, caixa, order)

    assert resp.status_code == 403, resp.content
    assert not _refunds("EST-403").exists()


# ── Mais de uma cobrança: cobrança por cobrança (#3134) ──────────────────────
#
# Decisão da coordenação em 22/11/2026, reversível: o Gerente estorna cobrança por
# cobrança, vendo o valor de cada uma separado. A tela NUNCA mostra o total do pedido.


def _second_charge(order: Order, amount_q: int, *, method: str = "pix") -> str:
    ref = f"INT-{order.ref}-2"
    PaymentService.create_intent(order.ref, amount_q, method, gateway="mock", ref=ref)
    PaymentService.authorize(ref, gateway_id=f"gw-{ref}")
    PaymentService.capture(ref)
    return ref


def test_com_duas_cobrancas_a_porta_abre_para_a_escolha(client, gerente):
    order = _paid("EST-DUAS", total_q=3000)
    second = _second_charge(order, 800)

    action = _action(order, gerente)
    assert action.enabled, action.reason
    body = client.get(reverse("api-backstage-order-refund-preview", args=[order.ref])).json()

    assert body["choose"] is True
    assert body["choose_reason"] == "Este pedido tem mais de uma cobrança. Escolha qual estornar."
    assert [(row["intent_ref"], row["method_label"], row["paid_display"], row["available_display"]) for row in body["charges"]] == [
        ("INT-EST-DUAS", "Pix", "R$ 30,00", "R$ 30,00"),
        (second, "Pix", "R$ 8,00", "R$ 8,00"),
    ]
    # O total do pedido (R$ 38,00) não aparece em lugar nenhum.
    assert "38,00" not in str(body) and "3800" not in str(body)


def test_a_cobranca_escolhida_mostra_so_o_valor_dela(client, gerente):
    order = _paid("EST-ESCOLHA", total_q=3000)
    second = _second_charge(order, 800)

    url = reverse("api-backstage-order-refund-preview", args=[order.ref])
    body = client.get(url, {"intent": second}).json()

    assert body["choose"] is False and body["intent_ref"] == second
    assert (body["paid_display"], body["available_display"], body["available_q"]) == ("R$ 8,00", "R$ 8,00", 800)
    assert len(body["charges"]) == 2, "a escolha segue na tela, para trocar"
    assert body["action"]["enabled"] is True
    assert "38,00" not in str(body)


def test_estorna_so_a_cobranca_escolhida(client, gerente):
    order = _paid("EST-SO-UMA", total_q=3000)
    second = _second_charge(order, 800)
    gateway = Gateway()
    base = order_refund.revision(order, order_refund.plan(order, intent_ref=second))

    with patch(ADAPTER, return_value=gateway):
        resp = _refund(client, gerente, order, base=base, intent_ref=second, amount_q=500)

    assert resp.status_code == 200, resp.content
    assert resp.json()["refund"] == {"outcome": "refunded", "amount_q": 500, "refunded_q": 500, "available_q": 300, "message": ""}
    (call,) = gateway.calls
    assert (call["intent_ref"], call["amount_q"]) == (second, 500)
    assert PaymentService.refunded_total(second) == 500
    assert PaymentService.refunded_total("INT-EST-SO-UMA") == 0


def test_sem_escolher_a_cobranca_nada_sai(client, gerente):
    order = _paid("EST-SEM-ESCOLHA", total_q=3000)
    _second_charge(order, 800)
    gateway = Gateway()

    with patch(ADAPTER, return_value=gateway):
        resp = _refund(client, gerente, order)

    assert resp.status_code == 409, resp.content
    assert resp.json()["detail"] == "Este pedido tem mais de uma cobrança. Escolha qual estornar."
    assert gateway.calls == []


def test_cobranca_de_outro_pedido_e_recusada(client, gerente):
    order = _paid("EST-ALHEIA", total_q=3000)
    _second_charge(order, 800)
    other = _paid("EST-OUTRO", total_q=900)
    gateway = Gateway()
    base = order_refund.revision(order, order_refund.plan(order, intent_ref=f"INT-{other.ref}"))

    with patch(ADAPTER, return_value=gateway):
        resp = _refund(client, gerente, order, base=base, intent_ref=f"INT-{other.ref}")

    assert resp.status_code == 409, resp.content
    assert resp.json()["detail"] == "Esta cobrança não é deste pedido. Abra o estorno de novo."
    assert gateway.calls == []
