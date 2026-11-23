"""Balcão: "Consumir aqui" ou "Para levar" (#3193, opção A do dono).

O chip do balcão dizia "Consumir aqui" e era a porta da encomenda: quem queria
levar não tinha opção. Agora a comanda de balcão guarda a escolha
(``Session.data.pos.counter_service``), o pedido a leva no bloco ``pos``, e a
Cozinha a lê no lugar de "Retirada": no card e na via impressa.
"""

from __future__ import annotations

import pytest
from shopman.orderman.models import Order, Session

from shopman.backstage.projections.kds import counter_service_label
from shopman.backstage.projections.pos import build_open_tab
from shopman.shop.services import pos
from shopman.shop.services.pos_intent import PosIntentError, parse_pos_sale_intent
from shopman.shop.tests.test_pos_sales_mode import order_payload
from shopman.shop.tests.test_pos_scheduled_order import _close, _payload, balcao  # noqa: F401

pytestmark = pytest.mark.django_db


def _save(operator, shift, *, tab_ref: str, **extra) -> Session:
    session = pos.open_pos_tab(channel_ref="pdv", tab_ref=tab_ref, actor="t", operator_username=operator.username)
    payload = _payload(shift, client_request_id=f"cs-{tab_ref}", tab_ref=tab_ref,
                       tab_session_key=session.session_key, **extra)
    pos.save_pos_tab(channel_ref="pdv", payload=payload, actor="t", operator_username=operator.username)
    session.refresh_from_db()
    return session


def test_a_comanda_de_balcao_guarda_para_levar_e_reabre_com_ele(balcao):  # noqa: F811
    operator, shift = balcao

    session = _save(operator, shift, tab_ref="7", sales_mode="counter", counter_service="to_go")

    assert session.data["pos"]["counter_service"] == "to_go"
    assert build_open_tab(session)["counter_service"] == "to_go"


def test_o_pedido_leva_a_escolha_do_balcao(balcao):  # noqa: F811
    operator, shift = balcao
    payload = _payload(shift, client_request_id="cs-close", sales_mode="counter", counter_service="here")

    result = _close(operator, payload)

    assert Order.objects.get(ref=result.order_ref).data["pos"]["counter_service"] == "here"


def test_na_encomenda_quem_fala_e_o_recebimento(balcao):  # noqa: F811
    operator, shift = balcao

    session = _save(operator, shift, tab_ref="8", **order_payload(counter_service="to_go"))

    assert session.data["pos"]["counter_service"] == ""


def test_valor_desconhecido_recusa_com_o_campo():
    with pytest.raises(PosIntentError) as refused:
        parse_pos_sale_intent({"sales_mode": "counter", "items": [], "counter_service": "delivery"}, for_commit=False)

    assert refused.value.code == "invalid_counter_service"
    assert refused.value.focus == "fulfillment"


@pytest.mark.parametrize("data,label", [
    ({"pos": {"sales_mode": "counter", "counter_service": "to_go"}}, "Para levar"),
    ({"pos": {"sales_mode": "counter", "counter_service": "here"}}, "Consumir aqui"),
    # O balcão que ainda não disse (venda anterior a isto) segue "Retirada".
    ({"pos": {"sales_mode": "counter"}}, ""),
    ({"pos": {"sales_mode": "order", "counter_service": "to_go"}}, ""),
    # Pedido de outro canal não tem o bloco do PDV.
    ({}, ""),
])
def test_a_cozinha_le_a_escolha_do_balcao(data, label):
    assert counter_service_label(data) == label
