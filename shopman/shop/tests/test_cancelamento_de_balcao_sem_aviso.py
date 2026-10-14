"""P2-25: venda de balcão cancelada não avisa o cliente.

O cliente identificado no balcão está na frente do caixa quando a venda é
cancelada. "Seu pedido foi cancelado" chegava a quem nunca fez pedido nenhum.
Encomenda e entrega do PDV, e os canais remotos, continuam avisando.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from shopman.shop.config import ChannelConfig
from shopman.shop.lifecycle import dispatch


@pytest.fixture(autouse=True)
def _isolate_cancel_side_effects():
    with (
        patch("shopman.shop.lifecycle._mark_phase_complete"),
        patch("shopman.shop.lifecycle.ChannelConfig") as config_cls,
        patch("shopman.shop.lifecycle.stock"),
        patch("shopman.shop.lifecycle.payment"),
        patch("shopman.shop.lifecycle.loyalty"),
        patch("shopman.shop.lifecycle.fiscal"),
        patch("shopman.shop.services.kds.cancel_tickets"),
        patch("shopman.shop.services.courier.on_order_cancelled"),
    ):
        config_cls.for_channel.return_value = ChannelConfig()
        yield


def _order(*, channel_ref: str, data: dict) -> MagicMock:
    order = MagicMock()
    order.ref = "PDV-001"
    order.status = "cancelled"
    order.channel_ref = channel_ref
    order.data = {"customer": {"phone": "+5543999990000"}, **data}
    order.snapshot = {"items": [], "data": {}}
    return order


_BALCAO = {
    "origin_channel": "pos",
    "fulfillment_type": "pickup",
    "pos": {"sales_mode": "counter"},
    "payment": {"method": "cash"},
}


@patch("shopman.shop.lifecycle.notification")
def test_venda_de_balcao_cancelada_nao_avisa(mock_notification):
    dispatch(_order(channel_ref="pdv", data=_BALCAO), "on_cancelled")

    mock_notification.send.assert_not_called()


@pytest.mark.parametrize("data", [
    pytest.param({**_BALCAO, "pos": {"sales_mode": "order"}, "delivery_date": "2099-01-01"}, id="encomenda-retirada"),
    pytest.param({**_BALCAO, "pos": {"sales_mode": "order"}, "fulfillment_type": "delivery"}, id="encomenda-entrega"),
    pytest.param({**_BALCAO, "payment": {"method": "link"}}, id="link-de-pagamento"),
])
@patch("shopman.shop.lifecycle.notification")
def test_encomenda_do_pdv_cancelada_segue_avisando(mock_notification, data):
    dispatch(_order(channel_ref="pdv", data=data), "on_cancelled")

    assert mock_notification.send.call_args.args[1] == "order_cancelled"


@patch("shopman.shop.lifecycle.notification")
def test_pedido_remoto_cancelado_segue_avisando(mock_notification):
    data = {"origin_channel": "web", "fulfillment_type": "pickup"}

    dispatch(_order(channel_ref="web", data=data), "on_cancelled")

    assert mock_notification.send.call_args.args[1] == "order_cancelled"
