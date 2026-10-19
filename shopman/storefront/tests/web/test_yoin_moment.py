"""O yoin marca o pedido GARANTIDO, não a primeira visita.

Brecha real: com Pix/cartão o checkout manda o cliente para a tela de pagamento.
Se ele clicasse em "Acompanhar pedido" sem pagar, o acompanhamento carregava
pela primeira vez, consumia a marca e soltava o confete, comemorando um pedido
que ainda podia expirar.

Quem sabe que o pedido ACABOU de ser fechado é o navegador do checkout
(``surfaces/storefront-nuxt/app/utils/justPlaced.ts``); o servidor só diz, numa
leitura sem efeito, se o pedido já pode ser comemorado (``placement_secured``).
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.django_db


def _tracking(client, ref: str) -> dict:
    resposta = client.get(f"/api/v1/tracking/{ref}/")
    assert resposta.status_code == 200, resposta.status_code
    return resposta.json()


class TestPedidoQueAindaDevePagamento:
    def test_nao_comemora_enquanto_falta_pagar(self, client, order_with_payment):
        from shopman.orderman.models import Order as _Order

        _Order.objects.filter(pk=order_with_payment.pk).update(status="accepted")

        dados = _tracking(client, order_with_payment.ref)

        assert dados["placement_secured"] is False
        assert dados["payment_due"] is True


class TestPedidoSemPagamentoPendente:
    def test_comemora_quando_nao_ha_o_que_pagar(self, client, order):
        """Dinheiro/balcão: colocar o pedido JÁ é a conclusão do ato."""
        dados = _tracking(client, order.ref)

        assert dados["placement_secured"] is True
        assert dados["payment_due"] is False

    def test_a_leitura_nao_consome_nada(self, client, order):
        """O GET é leitura: a segunda visita responde igual à primeira."""
        sessao_antes = dict(client.session.items())

        assert _tracking(client, order.ref)["placement_secured"] is True
        assert _tracking(client, order.ref)["placement_secured"] is True
        assert dict(client.session.items()) == sessao_antes


class TestPedidoMorto:
    def test_nao_comemora_pedido_cancelado(self, client, order):
        """Cancelado antes da primeira visita: confete sobre tela de cancelamento."""
        from shopman.orderman.models import Order as _Order

        _Order.objects.filter(pk=order.pk).update(status="cancelled")

        assert _tracking(client, order.ref)["placement_secured"] is False
