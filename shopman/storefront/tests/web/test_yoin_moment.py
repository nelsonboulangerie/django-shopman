"""O yoin marca o pedido GARANTIDO, não a primeira visita.

Brecha real: com Pix/cartão o checkout manda o cliente para a tela de pagamento.
Se ele clicasse em "Acompanhar pedido" sem pagar, o acompanhamento carregava
pela primeira vez, consumia `just_placed` e soltava o confete — comemorando um
pedido que ainda podia expirar. Pior: como o consumo é de uso único, a
comemoração se perdia para sempre, justamente antes do momento em que ela faz
sentido (a volta depois de pagar).
"""
from __future__ import annotations

import pytest

from shopman.shop.services.customer_orders import JUST_PLACED_SESSION_KEY

pytestmark = pytest.mark.django_db


def _armar_momento(client, ref: str) -> None:
    sessao = client.session
    sessao[JUST_PLACED_SESSION_KEY] = ref
    sessao.save()


def _just_placed(client, ref: str):
    resposta = client.get(f"/api/v1/tracking/{ref}/")
    assert resposta.status_code == 200, resposta.status_code
    return resposta.json().get("just_placed")


class TestPedidoQueAindaDevePagamento:
    def test_nao_comemora_enquanto_falta_pagar(self, client, order_with_payment):
        from shopman.orderman.models import Order as _Order

        _Order.objects.filter(pk=order_with_payment.pk).update(status="accepted")
        _armar_momento(client, order_with_payment.ref)

        assert _just_placed(client, order_with_payment.ref) is False

    def test_a_comemoracao_sobrevive_para_depois_do_pagamento(self, client, order_with_payment):
        """A flag não pode ser queimada na visita que não comemora."""
        from shopman.orderman.models import Order as _Order

        _Order.objects.filter(pk=order_with_payment.pk).update(status="accepted")
        _armar_momento(client, order_with_payment.ref)

        _just_placed(client, order_with_payment.ref)  # visita sem pagar

        assert client.session.get(JUST_PLACED_SESSION_KEY) == order_with_payment.ref


class TestPedidoSemPagamentoPendente:
    def test_comemora_quando_nao_ha_o_que_pagar(self, client, order):
        """Dinheiro/balcão: colocar o pedido JÁ é a conclusão do ato."""
        _armar_momento(client, order.ref)

        assert _just_placed(client, order.ref) is True

    def test_comemora_uma_vez_so(self, client, order):
        _armar_momento(client, order.ref)

        assert _just_placed(client, order.ref) is True
        assert _just_placed(client, order.ref) is False


class TestPedidoMorto:
    def test_nao_comemora_pedido_cancelado(self, client, order):
        """Cancelado antes da primeira visita: confete sobre tela de cancelamento."""
        from shopman.orderman.models import Order as _Order

        _Order.objects.filter(pk=order.pk).update(status="cancelled")
        _armar_momento(client, order.ref)

        assert _just_placed(client, order.ref) is False
