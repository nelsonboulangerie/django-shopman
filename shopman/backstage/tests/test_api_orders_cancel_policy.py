"""Cancelamento pelo operador — as três camadas, e a que faltava.

Antes, ``POST /orders/<ref>/cancel/`` num pedido que a máquina de estados não
deixava cancelar respondia ``200 {"ok": true}`` e não cancelava nada: sem
estorno, sem aviso ao marketplace, sem uma linha de erro na tela. O operador
fechava o diálogo achando que tinha cancelado.

O conserto tem três camadas, e cada teste aqui prende uma delas:

  régua       — ``snapshot.lifecycle.transitions``: é possível para ESTE pedido?
  política    — ``operator_cancel_policy``: é permitido agora, olhando o ciclo
                do PAGAMENTO, que é separado do ciclo do pedido?
  autorização — a view: ESTE ator pode?

A régua vem do canal e é assada no pedido; por isso os pedidos deste arquivo
declaram o próprio ``snapshot``, em vez de depender do seed.
"""

from __future__ import annotations

import pytest
from django.contrib.auth.models import Permission, User
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse
from shopman.orderman.models import Order, OrderItem

from shopman.shop.models import Shop

# A régua do canal de balcão: cancela na esteira, cancela depois de fechada, e
# — com o conserto — cancela também com o pão pronto no balcão. `dispatched` e
# `delivered` NÃO entram: quando o motoboy saiu, o fato é devolução.
REGUA_DO_CANAL = {
    "new": ["accepted", "cancelled"],
    "accepted": ["preparing", "ready", "completed", "cancelled"],
    "preparing": ["ready", "cancelled"],
    "ready": ["preparing", "dispatched", "completed", "cancelled"],
    "dispatched": ["delivered", "returned"],
    "delivered": ["completed", "returned"],
    "completed": ["returned", "cancelled"],
    "cancelled": [],
    "returned": [],
}


def _perm(codename: str) -> Permission:
    return Permission.objects.get(
        content_type=ContentType.objects.get(app_label="shop", model="shop"),
        codename=codename,
    )


@pytest.fixture
def shop(db):
    return Shop.objects.create(name="Loja")


@pytest.fixture
def caixa(db, shop):
    """Quem opera a fila: `manage_orders` e nada além."""
    user = User.objects.create_user("caixa", password="pw", is_staff=True)
    user.user_permissions.add(_perm("manage_orders"))
    return user


@pytest.fixture
def gerente(db, shop):
    """Quem opera a fila E cancela o que já passou do preparo."""
    user = User.objects.create_user("gerente", password="pw", is_staff=True)
    user.user_permissions.add(_perm("manage_orders"), _perm("cancel_advanced_order"))
    return user


def _order(ref: str, status: str, *, regua: dict | None = None) -> Order:
    order = Order.objects.create(
        ref=ref,
        channel_ref="pdv",
        status=status,
        total_q=1500,
        data={"customer": {"name": "Ana"}, "payment": {"method": "cash"}},
        snapshot={"lifecycle": {"transitions": regua if regua is not None else REGUA_DO_CANAL}},
    )
    OrderItem.objects.create(
        order=order, line_id="1", sku="SKU", name="Pão", qty=1, unit_price_q=1500, line_total_q=1500
    )
    return order


def _cancel(client, order, **payload):
    return client.post(
        reverse("api-backstage-order-cancel", args=[order.ref]),
        data=payload or {"reason": "cliente desistiu"},
        content_type="application/json",
    )


# ── A camada que faltava: a resposta deixa de mentir ────────────────────────


@pytest.mark.django_db
def test_status_fora_da_regua_devolve_409_e_nao_200_mentiroso(client, gerente):
    """O bug original: 200 {"ok": true} com o pedido intacto.

    `completed` sem `cancelled` na régua é o caso mais direto de "a régua não
    deixa" — e antes deste conserto a view respondia sucesso mesmo assim.
    """
    regua = dict(REGUA_DO_CANAL, completed=["returned"])
    order = _order("CANCEL-409", "completed", regua=regua)
    client.force_login(gerente)

    resp = _cancel(client, order)

    assert resp.status_code == 409, resp.content
    order.refresh_from_db()
    assert order.status == "completed"
    assert "não pode ser cancelado" in resp.json()["detail"]


# ── Autorização: quem pode cancelar depois de pronto ────────────────────────


@pytest.mark.django_db
def test_caixa_nao_cancela_pedido_pronto(client, caixa):
    order = _order("CANCEL-CAIXA", "ready")
    client.force_login(caixa)

    resp = _cancel(client, order)

    assert resp.status_code == 403, resp.content
    assert resp.json()["error"]["code"] == "cancel_requires_manager"
    order.refresh_from_db()
    assert order.status == "ready"


@pytest.mark.django_db
def test_gerente_cancela_pedido_pronto(client, gerente):
    order = _order("CANCEL-GERENTE", "ready")
    client.force_login(gerente)

    resp = _cancel(client, order)

    assert resp.status_code == 200, resp.content
    order.refresh_from_db()
    assert order.status == "cancelled"


@pytest.mark.django_db
@pytest.mark.parametrize("status", ["new", "accepted", "preparing"])
def test_esteira_normal_continua_sendo_do_caixa(client, caixa, status):
    """Regressão: o degrau novo não pode subir a régua do cancelamento comum."""
    order = _order(f"CANCEL-OK-{status}", status)
    client.force_login(caixa)

    resp = _cancel(client, order)

    assert resp.status_code == 200, resp.content
    order.refresh_from_db()
    assert order.status == "cancelled"


# ── Política: o ciclo do pagamento é separado do ciclo do pedido ────────────


@pytest.mark.django_db
def test_pedido_pago_exige_segunda_assinatura(client, gerente, monkeypatch):
    """Dinheiro capturado não impede cancelar — exige duas pessoas.

    É a régua que o PDV já aplicava só no seu próprio endpoint ("cancelar venda
    fechada é exceção auditada"), agora valendo para todo caminho de operador.
    """
    from shopman.shop.services import payment_status

    monkeypatch.setattr(payment_status, "has_sufficient_captured_payment", lambda order: True)
    order = _order("CANCEL-PAGO", "preparing")
    client.force_login(gerente)

    resp = _cancel(client, order)

    # 422, não 403: falta um dado no payload (a assinatura), não permissão do
    # ator — é o mesmo status e o mesmo `error.code` que o desafio de gerente do
    # PDV já devolve, para a tela tratar os dois no mesmo lugar.
    assert resp.status_code == 422, resp.content
    assert resp.json()["error"]["code"] == "manager_approval_required"
    order.refresh_from_db()
    assert order.status == "preparing"


@pytest.mark.django_db
def test_pagamento_ilegivel_falha_fechado(client, gerente, monkeypatch):
    """Sem conseguir ler o pagamento, trate como se houvesse dinheiro em jogo.

    O custo do erro para um lado é uma assinatura a mais; para o outro é
    cancelar um pedido pago sem ninguém saber.
    """
    from shopman.shop.services import payment_status

    def _explode(order):
        raise RuntimeError("payman fora do ar")

    monkeypatch.setattr(payment_status, "has_sufficient_captured_payment", _explode)
    order = _order("CANCEL-CEGO", "preparing")
    client.force_login(gerente)

    resp = _cancel(client, order)

    assert resp.status_code == 422, resp.content
    assert resp.json()["error"]["code"] == "manager_approval_required"


# ── A tela não decide: a mesma pergunta, dois perfis, duas respostas ────────


@pytest.mark.django_db
def test_can_cancel_difere_por_perfil_no_mesmo_pedido(caixa, gerente):
    """A prova de que o servidor decide a capacidade e a UI não recalcula."""
    from shopman.backstage.projections.order_queue import build_operator_order

    order = _order("CANCEL-CAP", "ready")

    assert build_operator_order(order, user=gerente).can_cancel is True
    projecao_caixa = build_operator_order(order, user=caixa)
    assert projecao_caixa.can_cancel is False
    assert "do gerente" in projecao_caixa.cancel_block_label


@pytest.mark.django_db
def test_capability_avisa_o_desafio_antes_de_o_operador_digitar(gerente, monkeypatch):
    from shopman.backstage.projections.order_queue import build_operator_order
    from shopman.shop.services import payment_status

    monkeypatch.setattr(payment_status, "has_sufficient_captured_payment", lambda order: True)
    order = _order("CANCEL-CAP-PAGO", "preparing")

    projecao = build_operator_order(order, user=gerente)

    assert projecao.can_cancel is True
    assert projecao.cancel_requires_approval is True
