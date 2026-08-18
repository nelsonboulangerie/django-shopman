"""O shop grava a venda no livro-caixa (WP-3 do CASHMAN-PLAN, ADR-022).

Toda venda no terminal escreve UMA linha ``sale`` no livro do turno aberto do
operador: ``amount_q`` é o efeito em dinheiro na gaveta (zero para pix, cartão,
external e entrega paga na porta), ``payment_ref`` aponta o intent do dinheiro
no Payman, e o payload guarda método, recebido, troco e os intents por método.
Cancelar grava ``refund`` na gaveta de quem devolve; o acerto de entrega grava
``cod_settled`` na gaveta de quem recebeu. Nada disso é etiqueta no pedido.
"""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.test import override_settings
from shopman.cashman import Entry
from shopman.cashman import services as cash
from shopman.orderman.models import Order
from shopman.payman import PaymentService
from shopman.payman.models import PaymentIntent

from shopman.shop.models import Channel, Shop
from shopman.shop.services import operator_orders
from shopman.shop.services import pos as pos_service
from shopman.shop.services.pos_intent import PosIntentError

pytestmark = pytest.mark.django_db

_MOCK_ADAPTERS = override_settings(
    SHOPMAN_PAYMENT_ADAPTERS={
        "pix": "shopman.shop.adapters.payment_mock",
        "card": "shopman.shop.adapters.payment_mock",
        "cash": None,
        "external": None,
    }
)


class _Counter:
    """Um balcão: canal PDV, um item, um operador com turno aberto e fundo de R$ 100."""

    def __init__(self):
        from shopman.offerman.models import Product

        Shop.objects.create(name="Test Shop", brand_name="Test")
        Channel.objects.create(
            ref="pdv",
            name="PDV",
            is_active=True,
            config={
                "confirmation": {"mode": "immediate"},
                "payment": {"method": "cash", "timing": "external"},
                "stock": {"check_on_commit": False},
            },
        )
        Product.objects.create(sku="PAO", name="Pão", base_price_q=1200, is_published=True, is_sellable=True)
        self.operator = get_user_model().objects.create_user(username="marina", password="x")
        self.shift = cash.open_shift(operator=self.operator, float_q=10000)

    def close(self, *, client_request_id: str, shift=None, operator=None, **overrides):
        payload = {
            "items": [{"sku": "PAO", "name": "Pão", "qty": 1, "unit_price_q": 1200}],
            "customer_name": "Cliente",
            "payment_method": "cash",
            "client_request_id": client_request_id,
            "cash_shift_id": (shift or self.shift).pk,
        }
        payload.update(overrides)
        operator = operator or self.operator
        return pos_service.close_sale(
            channel_ref="pdv",
            payload=payload,
            actor=f"pos:{operator.username}",
            operator_username=operator.username,
        )

    def sale_lines(self, shift=None):
        return list(Entry.objects.filter(shift=shift or self.shift, kind=Entry.Kind.SALE).order_by("id"))


@pytest.fixture
def counter():
    return _Counter()


# ── A linha `sale` ────────────────────────────────────────────────────────


def test_venda_em_dinheiro_grava_uma_linha_com_o_efeito_na_gaveta(counter):
    """Cliente entrega R$ 20 por R$ 12: entra R$ 12 na gaveta; troco fica no payload."""
    result = counter.close(
        client_request_id="c1",
        payment_tenders=[{"method": "cash", "amount_q": 2000, "collection": "terminal"}],
        tendered_amount_q=2000,
    )

    (line,) = counter.sale_lines()
    intent = PaymentIntent.objects.get(order_ref=result.order_ref)
    assert line.amount_q == 1200
    assert line.order_ref == result.order_ref
    assert line.payment_ref == intent.ref
    assert line.operator == counter.operator
    assert line.payload["method"] == "cash"
    assert line.payload["received_q"] == 2000
    assert line.payload["change_q"] == 800
    assert line.payload["intents"] == {"cash": intent.ref}
    assert cash.balance(counter.shift) == 11200


@_MOCK_ADAPTERS
def test_venda_em_pix_passa_pelo_turno_sem_tocar_na_gaveta(counter):
    """Pix sozinho vai ao gateway; a linha existe (a venda é deste turno) com efeito zero."""
    result = counter.close(client_request_id="c2", payment_method="pix")

    (line,) = counter.sale_lines()
    order = Order.objects.get(ref=result.order_ref)
    assert line.amount_q == 0
    assert line.payload["method"] == "pix"
    assert line.payment_ref == order.data["payment"]["intent_ref"]
    assert cash.balance(counter.shift) == 10000
    # O PDV recebe o que exibir (QR do mock).
    assert result.payment.get("method") == "pix"


def test_venda_mista_e_uma_linha_com_o_dinheiro_e_todos_os_intents(counter):
    result = counter.close(
        client_request_id="c3",
        payment_tenders=[
            {"method": "cash", "amount_q": 500, "collection": "terminal"},
            {"method": "external", "amount_q": 700, "collection": "terminal"},
        ],
    )

    (line,) = counter.sale_lines()
    intents = {i.method: i for i in PaymentIntent.objects.filter(order_ref=result.order_ref)}
    assert line.amount_q == 500
    assert line.payment_ref == intents["cash"].ref
    assert line.payload["method"] == "mixed"
    assert line.payload["intents"] == {"cash": intents["cash"].ref, "external": intents["external"].ref}
    assert cash.balance(counter.shift) == 10500


def test_pix_numa_venda_mista_e_atestado_no_balcao(counter):
    """Pix dentro de mista não passa por gateway (QR estático): o intent nasce
    atestado, e a reconciliação vê que foi o balcão, não o gateway."""
    result = counter.close(
        client_request_id="c4",
        payment_tenders=[
            {"method": "cash", "amount_q": 200, "collection": "terminal"},
            {"method": "pix", "amount_q": 1000, "collection": "terminal"},
        ],
    )

    pix = PaymentIntent.objects.get(order_ref=result.order_ref, method="pix")
    assert pix.status == PaymentIntent.Status.CAPTURED
    assert pix.gateway == ""
    assert pix.gateway_data["asserted_at_terminal"] is True
    (line,) = counter.sale_lines()
    assert line.amount_q == 200


def test_entrega_paga_na_porta_e_venda_deste_turno_sem_dinheiro_ainda(counter):
    result = counter.close(
        client_request_id="c5",
        fulfillment_type="delivery",
        payment_collection="on_delivery",
        delivery_address="Rua das Flores, 1",
        customer_phone="+5543999990001",
    )

    (line,) = counter.sale_lines()
    assert line.amount_q == 0
    assert line.payload["collection"] == "on_delivery"
    assert line.payment_ref == ""
    assert not PaymentIntent.objects.filter(order_ref=result.order_ref).exists()


def test_repetir_a_venda_nao_duplica_a_linha(counter):
    first = counter.close(client_request_id="c6", tendered_amount_q=1200)
    second = counter.close(client_request_id="c6", tendered_amount_q=1200)

    assert first.order_ref == second.order_ref
    assert len(counter.sale_lines()) == 1


# ── Sem turno não há venda; e o pedido não carrega etiqueta de turno ─────


def test_sem_turno_aberto_a_venda_e_recusada_antes_do_commit(counter):
    other = get_user_model().objects.create_user(username="sem-turno", password="x")
    before = Order.objects.count()

    with pytest.raises(PosIntentError) as exc:
        counter.close(client_request_id="c7", cash_shift_id=None, operator=other)
    assert exc.value.code == "cash_shift_required"
    assert exc.value.status == 409
    assert Order.objects.count() == before


def test_turno_fechado_tambem_recusa(counter):
    cash.close_shift(counter.shift, counted_q=10000, actor=counter.operator)
    with pytest.raises(PosIntentError) as exc:
        counter.close(client_request_id="c8")
    assert exc.value.code == "cash_shift_required"


def test_o_pedido_nao_carrega_etiqueta_de_turno(counter):
    """A atribuição da venda ao turno É a linha do livro; o pedido só sabe o terminal."""
    result = counter.close(
        client_request_id="c9",
        payment_tenders=[{"method": "cash", "amount_q": 1200, "collection": "terminal"}],
        pos_terminal_ref="pdv-main",
    )

    order = Order.objects.get(ref=result.order_ref)
    assert "cash_shift_id" not in (order.data.get("pos") or {})
    assert order.data["pos"]["terminal_ref"] == "pdv-main"
    for tender in order.data["payment"]["tenders"]:
        assert "cash_shift_id" not in tender


# ── Devolução: o dinheiro sai da gaveta de agora ─────────────────────────


def test_cancelar_venda_em_dinheiro_grava_refund_na_gaveta_de_quem_devolve(counter, django_capture_on_commit_callbacks):
    result = counter.close(client_request_id="c10", tendered_amount_q=1200)
    (sale_line,) = counter.sale_lines()

    with django_capture_on_commit_callbacks(execute=True):
        pos_service.cancel_recent_order(order_ref=result.order_ref, actor="pos:marina")

    refund = Entry.objects.get(shift=counter.shift, kind=Entry.Kind.REFUND)
    assert refund.amount_q == -1200
    assert refund.parent == sale_line
    assert refund.order_ref == result.order_ref
    assert refund.payment_ref == sale_line.payment_ref
    assert cash.balance(counter.shift) == 10000
    intent = PaymentService.get(sale_line.payment_ref)
    assert intent.status == PaymentIntent.Status.REFUNDED


def test_devolver_por_outro_turno_aponta_a_venda_mas_nao_o_parent(counter, django_capture_on_commit_callbacks):
    """Quem devolve tem outro turno: o dinheiro sai DESSA gaveta; ``parent`` só
    liga linhas do mesmo livro, então fica vazio e o ``order_ref`` liga as duas."""
    result = counter.close(client_request_id="c11", tendered_amount_q=1200)
    manager = get_user_model().objects.create_user(username="pablo", password="x")
    from shopman.cashman import Terminal

    other_shift = cash.open_shift(operator=manager, terminal=Terminal.objects.create(ref="pdv-2"), float_q=0)

    with django_capture_on_commit_callbacks(execute=True):
        pos_service.cancel_recent_order(order_ref=result.order_ref, actor="pos:pablo")

    refund = Entry.objects.get(kind=Entry.Kind.REFUND)
    assert refund.shift == other_shift
    assert refund.parent is None
    assert cash.balance(other_shift) == -1200
    assert cash.balance(counter.shift) == 11200


def test_devolver_dinheiro_sem_turno_aberto_e_recusado_e_o_pedido_fica(counter):
    result = counter.close(client_request_id="c12", tendered_amount_q=1200)
    get_user_model().objects.create_user(username="sem-turno", password="x")

    with pytest.raises(ValueError, match="Abra o caixa"):
        pos_service.cancel_recent_order(order_ref=result.order_ref, actor="pos:sem-turno")

    assert Order.objects.get(ref=result.order_ref).status != Order.Status.CANCELLED
    assert not Entry.objects.filter(kind=Entry.Kind.REFUND).exists()


@_MOCK_ADAPTERS
def test_cancelar_venda_em_pix_nao_precisa_de_turno_nem_mexe_na_gaveta(counter, django_capture_on_commit_callbacks):
    result = counter.close(client_request_id="c13", payment_method="pix")
    get_user_model().objects.create_user(username="sem-turno", password="x")

    with django_capture_on_commit_callbacks(execute=True):
        pos_service.cancel_recent_order(order_ref=result.order_ref, actor="pos:sem-turno")

    assert Order.objects.get(ref=result.order_ref).status == Order.Status.CANCELLED
    assert not Entry.objects.filter(kind=Entry.Kind.REFUND).exists()


# ── Acerto de entrega: o turno que RECEBEU ────────────────────────────────


def _cod_order(ref: str, total_q: int = 3000) -> Order:
    return Order.objects.create(
        ref=ref,
        channel_ref="pdv",
        status=Order.Status.DISPATCHED,
        total_q=total_q,
        data={
            "fulfillment_type": "delivery",
            "payment": {
                "method": "cash",
                "collection": "on_delivery",
                "amount_q": total_q,
                "tenders": [{"method": "cash", "amount_q": total_q, "collection": "on_delivery", "status": "pending"}],
            },
        },
    )


def test_acerto_de_entrega_grava_cod_settled_no_turno_de_quem_recebeu(counter):
    order = _cod_order("COD-1")

    amount = operator_orders.settle_delivery_cash(order, cash_shift=counter.shift, actor="pos:marina")

    assert amount == 3000
    line = Entry.objects.get(shift=counter.shift, kind=Entry.Kind.COD_SETTLED)
    intent = PaymentIntent.objects.get(order_ref="COD-1")
    assert line.amount_q == 3000
    assert line.payment_ref == intent.ref
    assert intent.status == PaymentIntent.Status.CAPTURED
    assert intent.gateway_data["collection"] == "on_delivery"
    order.refresh_from_db()
    payment = order.data["payment"]
    assert payment["intent_ref"] == intent.ref
    assert payment["cod_settled_by"] == "pos:marina"
    assert "cod_cash_shift_id" not in payment and "cod_terminal_ref" not in payment
    assert payment["tenders"][0]["intent_ref"] == intent.ref
    assert "cash_shift_id" not in payment["tenders"][0]
    assert cash.balance(counter.shift) == 13000


def test_acerto_exige_turno_aberto_e_nao_repete(counter):
    order = _cod_order("COD-2")
    with pytest.raises(ValueError, match="turno"):
        operator_orders.settle_delivery_cash(order, cash_shift=None, actor="pos:marina")

    operator_orders.settle_delivery_cash(order, cash_shift=counter.shift, actor="pos:marina")
    order.refresh_from_db()
    with pytest.raises(ValueError, match="já foi acertado"):
        operator_orders.settle_delivery_cash(order, cash_shift=counter.shift, actor="pos:marina")
    assert Entry.objects.filter(kind=Entry.Kind.COD_SETTLED).count() == 1
