"""Conta do cliente (WP-10 do CASHMAN-PLAN): deve no Payman, paga no acerto, e só para quem tem conta.

- Venda "em conta" no PDV só para cliente identificado com ``metadata.house_account``;
  recusa ANTES do commit para os outros.
- A venda grava a linha ``sale`` com efeito ZERO (nada entrou na gaveta) e o intent
  ``account`` nasce AUTORIZADO (= deve); o saldo do cliente é derivado.
- Cancelar a venda em conta mata a dívida (intent cancelado), sem estorno.
- O acerto captura FIFO por venda inteira; em dinheiro, cada intent vira uma linha
  ``account_settled`` no turno de quem recebeu, na mesma transação.
"""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from shopman.cashman import Entry
from shopman.cashman import services as cash
from shopman.guestman.models import Customer
from shopman.orderman.models import Order
from shopman.payman import PaymentService
from shopman.payman.models import PaymentIntent

from shopman.shop.services import house_account, operator_orders
from shopman.shop.services.pos_intent import PosIntentError
from shopman.shop.tests.test_pos_cash_ledger import _Counter

pytestmark = pytest.mark.django_db


@pytest.fixture
def counter():
    return _Counter()


@pytest.fixture
def ana():
    return Customer.objects.create(ref="CLI-ANA", first_name="Ana", phone="+5543999990001", metadata={"house_account": True})


@pytest.fixture
def bia():
    return Customer.objects.create(ref="CLI-BIA", first_name="Bia", phone="+5543999990002")


def _sale_on_account(counter, *, customer_ref: str, client_request_id: str, total_q: int = 1200):
    return counter.close(
        client_request_id=client_request_id,
        payment_method="account",
        customer_ref=customer_ref,
        items=[{"sku": "PAO", "name": "Pão", "qty": total_q // 1200, "unit_price_q": 1200}],
    )


def test_venda_em_conta_so_para_cliente_com_conta(counter, ana, bia):
    with pytest.raises(PosIntentError) as exc:
        _sale_on_account(counter, customer_ref="CLI-BIA", client_request_id="c-bia")
    assert exc.value.code == "house_account_not_eligible"
    with pytest.raises(PosIntentError):
        counter.close(client_request_id="c-anon", payment_method="account")
    assert not Order.objects.exists()

    result = _sale_on_account(counter, customer_ref="CLI-ANA", client_request_id="c-ana")

    order = Order.objects.get(ref=result.order_ref)
    assert order.data["customer_ref"] == "CLI-ANA"
    intent = PaymentIntent.objects.get(order_ref=order.ref)
    assert (intent.method, intent.status, intent.amount_q) == ("account", "authorized", 1200)
    assert intent.gateway_data["customer_ref"] == "CLI-ANA"
    (line,) = counter.sale_lines()
    assert (line.amount_q, line.payload["method"], line.payload["intents"]) == (0, "account", {"account": intent.ref})
    assert cash.balance(counter.shift) == 10000  # nada entrou na gaveta
    assert house_account.balance_q("CLI-ANA") == 1200
    assert order.data["payment"]["intent_ref"] == intent.ref


def test_cancelar_venda_em_conta_mata_a_divida_sem_estorno(counter, ana, django_capture_on_commit_callbacks):
    result = _sale_on_account(counter, customer_ref="CLI-ANA", client_request_id="c-1")
    order = Order.objects.get(ref=result.order_ref)
    with django_capture_on_commit_callbacks(execute=True):
        operator_orders.cancel_order(order, reason="customer_requested", actor="gestor:pablo")

    intent = PaymentIntent.objects.get(order_ref=order.ref)
    assert intent.status == PaymentIntent.Status.CANCELLED
    assert intent.transactions.count() == 0
    assert house_account.balance_q("CLI-ANA") == 0
    assert not Entry.objects.filter(kind=Entry.Kind.REFUND).exists()


def test_acerto_fifo_por_venda_inteira_e_em_dinheiro_entra_na_gaveta(counter, ana):
    _sale_on_account(counter, customer_ref="CLI-ANA", client_request_id="c-1", total_q=1200)
    _sale_on_account(counter, customer_ref="CLI-ANA", client_request_id="c-2", total_q=2400)
    _sale_on_account(counter, customer_ref="CLI-ANA", client_request_id="c-3", total_q=1200)
    assert house_account.balance_q("CLI-ANA") == 4800
    (row,) = house_account.balances()
    assert (row.customer_ref, row.customer_name, row.balance_q, row.intents) == ("CLI-ANA", "Ana", 4800, 3)

    # R$ 30 cobre a 1ª (12) e a 2ª (24)? Não: 12 + 24 = 36 > 30. Captura só a 1ª.
    settlement = house_account.settle_account("CLI-ANA", 3000, "cash", shift=counter.shift, actor=counter.operator)
    assert (settlement.settled_q, settlement.remaining_q, len(settlement.intent_refs)) == (1200, 3600, 1)
    (line,) = Entry.objects.filter(kind=Entry.Kind.ACCOUNT_SETTLED)
    assert (line.amount_q, line.shift_id, line.payment_ref, line.payload["customer_ref"]) == (1200, counter.shift.pk, settlement.intent_refs[0], "CLI-ANA")
    assert cash.balance(counter.shift) == 11200
    intent = PaymentIntent.objects.get(ref=settlement.intent_refs[0])
    assert intent.status == PaymentIntent.Status.CAPTURED
    assert intent.gateway_data["settled_with"] == "cash"

    # Acerta o resto por pix (atestado no balcão): nada na gaveta, saldo zera.
    settlement = house_account.settle_account("CLI-ANA", 3600, "pix", actor=counter.operator)
    assert (settlement.settled_q, settlement.remaining_q) == (3600, 0)
    assert Entry.objects.filter(kind=Entry.Kind.ACCOUNT_SETTLED).count() == 1
    assert cash.balance(counter.shift) == 11200
    assert house_account.balances() == []


def test_acerto_recusa_o_que_nao_faz_sentido(counter, ana):
    _sale_on_account(counter, customer_ref="CLI-ANA", client_request_id="c-1", total_q=2400)
    with pytest.raises(house_account.HouseAccountError, match="turno"):
        house_account.settle_account("CLI-ANA", 2400, "cash", shift=None, actor=counter.operator)
    with pytest.raises(house_account.HouseAccountError, match="venda inteira"):
        house_account.settle_account("CLI-ANA", 1000, "cash", shift=counter.shift, actor=counter.operator)
    with pytest.raises(house_account.HouseAccountError, match="saldo"):
        house_account.settle_account("CLI-ZZZ", 1000, "pix", actor=counter.operator)
    with pytest.raises(house_account.HouseAccountError, match="Método"):
        house_account.settle_account("CLI-ANA", 2400, "bitcoin", actor=counter.operator)
    assert house_account.balance_q("CLI-ANA") == 2400
    assert not Entry.objects.filter(kind=Entry.Kind.ACCOUNT_SETTLED).exists()
    assert not get_user_model().objects.filter(username="ninguem").exists()
