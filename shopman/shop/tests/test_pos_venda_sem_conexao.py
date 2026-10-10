"""A venda que o PDV fez SEM CONEXÃO e enviou depois (WP-PDV-SEM-CONEXAO).

A fila do PDV reenvia o mesmo ``close_sale`` com o mesmo ``client_request_id``.
O servidor já é idempotente por essa chave; o que esta frente acrescenta é o
REGISTRO: o pedido diz que nasceu de uma venda sem conexão, quando o balcão
cobrou e de quando eram os preços da tela (``order.data.pos.offline``).
"""

from __future__ import annotations

import pytest
from shopman.orderman.models import Order

from shopman.shop.services.pos_intent import PosIntentError, parse_pos_sale_intent
from shopman.shop.tests.test_pos_cash_ledger import _Counter

pytestmark = pytest.mark.django_db


@pytest.fixture
def counter():
    return _Counter()


def test_venda_sem_conexao_grava_a_hora_da_cobranca_no_pedido(counter):
    result = counter.close(
        client_request_id="pos:offline-1",
        offline_captured_at="2026-10-10T14:32:05-03:00",
        offline_prices_at="2026-10-10T14:05:00-03:00",
    )

    order = Order.objects.get(ref=result.order_ref)
    assert order.data["pos"]["offline"] == {
        "captured_at": "2026-10-10T14:32:05-03:00",
        "prices_at": "2026-10-10T14:05:00-03:00",
    }


def test_reenvio_da_fila_devolve_a_mesma_venda(counter):
    first = counter.close(client_request_id="pos:offline-2", offline_captured_at="2026-10-10T17:32:05Z")
    again = counter.close(client_request_id="pos:offline-2", offline_captured_at="2026-10-10T17:32:05Z")

    assert again.order_ref == first.order_ref
    assert Order.objects.filter(data__client_request_id="pos:offline-2").count() == 1


def test_venda_com_conexao_nao_ganha_marca_de_offline(counter):
    result = counter.close(client_request_id="pos:online-1")

    assert "offline" not in (Order.objects.get(ref=result.order_ref).data.get("pos") or {})


def test_hora_sem_fuso_e_recusada():
    with pytest.raises(PosIntentError) as refused:
        parse_pos_sale_intent(
            {"items": [{"sku": "PAO", "qty": 1}], "offline_captured_at": "2026-10-10T14:32:05"},
        )

    assert refused.value.field == "offline_captured_at"
