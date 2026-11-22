"""Devolução de venda feita na CONTA DA CASA tira da conta só o valor devolvido (#2606).

Antes, o estorno da devolução cancelava todos os intents em aberto da conta do
pedido, e uma devolução PARCIAL apagava a dívida inteira. O Gestor recusava esses
pedidos com "a devolução ainda não passa pelo Gestor". O que esta suíte prende:

- a devolução parcial abate da conta só o devolvido, e o resto continua devido,
  para o mesmo cliente;
- a total zera a dívida do pedido;
- repetir a mesma devolução (retry) não abate duas vezes;
- a conta já acertada e a venda que mistura a conta com outra forma seguem com o
  Dono, com o motivo escrito;
- o diálogo diz para onde o valor vai ("saem da conta do cliente").
"""

from __future__ import annotations

import pytest
from shopman.orderman.models import Order
from shopman.payman import PaymentService
from shopman.payman.models import PaymentIntent

from shopman.backstage.projections import order_return
from shopman.shop.handlers.returns import ReturnService
from shopman.shop.services import payment as payment_service
from shopman.shop.tests import _no_show as world

pytestmark = [pytest.mark.django_db, pytest.mark.channels("web", "pdv")]

CLIENTE = "CLI-CONTA"


@pytest.fixture
def paes():
    world.make_shop()
    world.product("CROIS", price_q=1200)
    world.lot("CROIS")


def _vendido_na_conta(ref: str, *, qty: int = 2, payment: dict | None = None) -> Order:
    order = world.ready_order(ref, [("CROIS", qty, 1200)], payment=payment or {"method": "account"})
    intent = PaymentService.charge_to_account(
        order.ref, order.total_q, customer_ref=CLIENTE, idempotency_key=f"order-payment:{order.ref}:account:terminal",
    )
    order.data["payment"] = {**order.data["payment"], "intent_ref": intent.ref}
    order.data["customer_ref"] = CLIENTE
    order.save(update_fields=["data", "updated_at"])
    Order.objects.filter(pk=order.pk).update(status=Order.Status.COMPLETED)
    order.refresh_from_db()
    return order


def _devolver(order: Order, qty: int, *, index: int = 0) -> Order:
    line_id = order.items.first().line_id
    result = ReturnService.initiate_return(order, [{"line_id": line_id, "qty": qty}], reason="defeito", actor="gestor")
    assert result.success, result.error
    order.refresh_from_db()
    ReturnService.process_refund(order, 1200 * qty, "return.process", refund_reference=f"return:{order.ref}:{index}")
    order.refresh_from_db()
    return order


def test_devolucao_parcial_tira_da_conta_so_o_devolvido(paes):
    order = _vendido_na_conta("CONTA-PARCIAL")
    assert order_return.return_block_reason(order) == ""
    assert order_return.money_destination(order) == (True, "saem da conta do cliente.")

    _devolver(order, 1)

    assert payment_service.open_account_debt_q(order) == 1200
    assert PaymentService.account_balance_q(CLIENTE) == 1200
    (aberto,) = PaymentIntent.objects.filter(order_ref=order.ref, method="account", status="authorized")
    assert aberto.gateway_data["customer_ref"] == CLIENTE
    event = order.events.get(type="account_debt_reduced")
    assert event.payload["amount_q"] == 1200


def test_a_mesma_devolucao_repetida_nao_abate_duas_vezes(paes):
    order = _vendido_na_conta("CONTA-RETRY")
    _devolver(order, 1)

    ReturnService.process_refund(order, 1200, "return.process", refund_reference=f"return:{order.ref}:0")

    assert payment_service.open_account_debt_q(order) == 1200
    assert order.events.filter(type="account_debt_reduced").count() == 1


def test_devolucao_total_zera_a_divida_do_pedido(paes):
    order = _vendido_na_conta("CONTA-TOTAL")

    _devolver(order, 2)

    assert payment_service.open_account_debt_q(order) == 0
    assert PaymentService.account_balance_q(CLIENTE) == 0


def test_conta_ja_acertada_e_venda_mista_seguem_com_o_dono(paes):
    acertada = _vendido_na_conta("CONTA-ACERTADA")
    PaymentService.capture(acertada.data["payment"]["intent_ref"])
    mista = _vendido_na_conta(
        "CONTA-MISTA",
        payment={"method": "account", "tenders": [{"method": "account", "amount_q": 1200}, {"method": "cash", "amount_q": 1200}]},
    )

    assert order_return.return_block_reason(acertada) == "A conta deste pedido já foi acertada: a devolução dele é com o Dono."
    assert order_return.return_block_reason(mista) == (
        "Parte na conta da casa e parte em outra forma de pagamento: a devolução deste pedido é com o Dono."
    )


def test_cancelar_a_venda_na_conta_ainda_apaga_a_divida_inteira(paes):
    """O cancelamento comum (sem valor decidido) segue como sempre: a dívida morre com a venda."""
    order = _vendido_na_conta("CONTA-CANCELADA")

    payment_service.refund(order)

    assert payment_service.open_account_debt_q(order) == 0
    assert not order.events.filter(type="account_debt_reduced").exists()
