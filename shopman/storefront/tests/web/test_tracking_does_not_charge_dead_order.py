"""Acompanhamento de pedido morto não cria cobrança.

Todo GET de ``/api/v1/tracking/<ref>/`` chama ``ensure_payment_intent``. O Pix
da loja nasce só depois do aceite (``timing=post_commit``), então um pedido
recusado antes do aceite não tem intent — e a porta ``_payment_can_start``
liberava qualquer status diferente de ``new``. Resultado: recarregar a tela de
um pedido CANCELADO criava uma cobrança Pix nova (na Efí real, um QR pagável).
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from shopman.payman import PaymentService

from shopman.shop.services import customer_orders

pytestmark = pytest.mark.django_db


def _set(order, *, status: str, method: str = "pix"):
    from shopman.orderman.models import Order

    # `update` direto: a máquina de estados não deixa ir de `new` a `completed`,
    # e o que interessa aqui é o estado em que o pedido JÁ está.
    Order.objects.filter(pk=order.pk).update(status=status, data={"payment": {"method": method}})
    order.refresh_from_db()
    return order


def test_recarregar_acompanhamento_de_pix_cancelado_nao_cria_cobranca(order, client):
    _set(order, status="cancelled")

    resp = client.get(f"/api/v1/tracking/{order.ref}/")

    assert resp.status_code == 200
    assert list(PaymentService.get_by_order(order.ref)) == []
    order.refresh_from_db()
    assert not (order.data.get("payment") or {}).get("intent_ref")


@pytest.mark.parametrize("status", ["cancelled", "completed", "returned"])
@pytest.mark.parametrize("method", ["pix", "card"])
def test_pedido_terminal_nunca_inicia_pagamento(order, status, method):
    _set(order, status=status, method=method)

    with patch.object(customer_orders.payment_service, "initiate") as initiate:
        assert customer_orders.ensure_payment_intent(order) is False

    initiate.assert_not_called()


def test_pedido_aceito_continua_iniciando_o_pix(order):
    _set(order, status="accepted")

    with patch.object(customer_orders.payment_service, "initiate") as initiate:
        customer_orders.ensure_payment_intent(order)

    initiate.assert_called_once()
