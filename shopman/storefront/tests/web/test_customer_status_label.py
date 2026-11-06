"""Um estado só para o cliente: acompanhamento, lista da Conta e faixa da home.

Beta 06/11: um Pix gerado e não pago aparecia como "Aguardando a loja" na faixa
de pedido ativo da home e na lista de Meus pedidos, enquanto o acompanhamento
do mesmo pedido dizia que faltava pagar. A lista rotulava pelo ``order.status``
cru; o acompanhamento, pelo estado semântico que olha o pagamento. Agora as três
superfícies passam pela mesma função (``customer_status_label``).
"""

from __future__ import annotations

import pytest

from shopman.storefront.presentation.account import order_history_for_customer
from shopman.storefront.presentation.order_tracking import build_order_tracking

pytestmark = pytest.mark.django_db

PHONE = "5543999990001"


def _active_rows():
    # A faixa da home e a lista de pedidos em andamento da Conta leem estas
    # linhas (``/api/v1/account/orders/?filter=ativos`` e o ``summary``).
    return order_history_for_customer(phone=PHONE, filter_param="ativos")


def _capture(order):
    from shopman.payman import PaymentService

    intent = PaymentService.create_intent(order_ref=order.ref, amount_q=order.total_q, method="pix")
    order.data["payment"]["intent_ref"] = intent.ref
    order.save(update_fields=["data"])
    PaymentService.authorize(intent.ref)
    PaymentService.capture(intent.ref)
    order.refresh_from_db()


def test_pix_pendente_diz_que_falta_pagar_na_lista_e_na_faixa(order_with_payment):
    [row] = _active_rows()

    assert row["status"] == "new"
    assert row["status_label"] == "Aguardando pagamento"
    assert row["status_label"] == build_order_tracking(order_with_payment).status_label


def test_pago_esperando_aceite_diz_aguardando_a_loja(order_with_payment):
    _capture(order_with_payment)

    [row] = _active_rows()

    assert row["status"] == "new"
    assert row["status_label"] == "Aguardando a loja"
    assert row["status_label"] == build_order_tracking(order_with_payment).status_label


def test_dinheiro_parado_em_novo_diz_aguardando_a_loja(order):
    [row] = _active_rows()

    assert row["status_label"] == "Aguardando a loja"


def test_cartao_aceito_sem_captura_nao_diz_aceito(order_with_payment):
    from shopman.orderman.models import Order

    data = dict(order_with_payment.data)
    data["payment"] = {"method": "card", "status": "failed", "amount_q": order_with_payment.total_q}
    Order.objects.filter(pk=order_with_payment.pk).update(status="accepted", data=data)
    order_with_payment.refresh_from_db()

    [row] = _active_rows()

    assert row["status"] == "accepted"
    assert row["status_label"] == "Aguardando pagamento"
    assert row["status_label"] == build_order_tracking(order_with_payment).status_label
