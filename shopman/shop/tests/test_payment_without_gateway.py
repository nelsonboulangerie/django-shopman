"""Dinheiro e cobrança externa entram no livro do Payman (ADR-022, WP-2 do CASHMAN-PLAN).

``payment.initiate`` deixa de retornar cedo para ``cash``/``external``: quando a
coleta é no terminal (``payment.collection == "terminal"``, escrito pelo PDV) o
intent nasce capturado, com ``gateway=""``, e ``intent_ref`` vai para
``Order.data.payment`` como em pix/cartão. Sem ``collection`` (loja online) ou
com coleta na entrega (COD) nada muda: o intent nasce no acerto (WP-3).

``payment.refund`` deixa de ser no-op para dinheiro: o cancel de uma venda em
dinheiro grava ``PaymentTransaction(REFUND)`` no Payman, sem adapter.
"""

from __future__ import annotations

import pytest
from django.test import override_settings
from shopman.orderman.models import Order
from shopman.payman import PaymentService
from shopman.payman.models import PaymentIntent, PaymentTransaction

from shopman.shop.models import Channel, Shop
from shopman.shop.services import payment as payment_service
from shopman.shop.services import pos as pos_service

pytestmark = pytest.mark.django_db

_MOCK_ADAPTERS = override_settings(
    SHOPMAN_PAYMENT_ADAPTERS={
        "pix": "shopman.shop.adapters.payment_mock",
        "card": "shopman.shop.adapters.payment_mock",
        "cash": None,
        "external": None,
    }
)


def _order(ref: str, *, payment: dict, total_q: int = 5000, status=Order.Status.ACCEPTED, channel_ref="pdv"):
    return Order.objects.create(
        ref=ref,
        channel_ref=channel_ref,
        status=status,
        total_q=total_q,
        data={"payment": payment},
    )


def _intents(order_ref: str):
    return PaymentIntent.objects.filter(order_ref=order_ref)


# ── initiate: onde o intent de dinheiro nasce ───────────────────────────────


def test_initiate_cash_without_collection_creates_nothing():
    """Forma da loja online: ``{"method": "cash"}`` sem ``collection`` → sem intent."""
    order = _order("ORD-CASH-WEB", payment={"method": "cash", "change_for_q": 10000}, channel_ref="web")

    payment_service.initiate(order)

    order.refresh_from_db()
    assert "intent_ref" not in order.data["payment"]
    assert not _intents(order.ref).exists()


def test_initiate_cash_on_delivery_creates_nothing():
    """COD: o dinheiro só troca de mãos no acerto; o intent nasce lá (WP-3)."""
    order = _order(
        "ORD-CASH-COD",
        payment={
            "method": "cash",
            "collection": "on_delivery",
            "tenders": [{"method": "cash", "amount_q": 5000, "collection": "on_delivery", "status": "pending"}],
        },
    )

    payment_service.initiate(order)

    order.refresh_from_db()
    assert "intent_ref" not in order.data["payment"]
    assert not _intents(order.ref).exists()


def test_initiate_external_without_collection_creates_nothing():
    """Marketplace (iFood): ``external`` sem coleta no terminal continua fora do Payman aqui."""
    order = _order("ORD-EXT-MKT", payment={"method": "external"}, channel_ref="ifood")

    payment_service.initiate(order)

    assert not _intents(order.ref).exists()


def test_initiate_cash_at_terminal_creates_captured_intent_and_links_order():
    order = _order(
        "ORD-CASH-POS",
        payment={
            "method": "cash",
            "collection": "terminal",
            "amount_q": 5000,
            "tendered_q": 10000,
            "change_q": 5000,
            "tenders": [{"method": "cash", "amount_q": 5000, "collection": "terminal", "status": "received"}],
        },
    )

    payment_service.initiate(order)

    order.refresh_from_db()
    payment = order.data["payment"]
    intent = _intents(order.ref).get()
    assert payment["intent_ref"] == intent.ref
    assert payment["method"] == "cash"
    assert payment["amount_q"] == 5000
    # O intent vale o tender (o que ficou na gaveta), não o que o cliente entregou.
    assert intent.amount_q == 5000
    assert intent.method == PaymentIntent.Method.CASH
    assert intent.status == PaymentIntent.Status.CAPTURED
    assert intent.gateway == ""
    assert intent.gateway_id == ""
    assert intent.transactions.filter(type=PaymentTransaction.Type.CAPTURE, amount_q=5000).count() == 1
    assert payment_service.get_payment_status(order) == "captured"
    assert payment_service.has_sufficient_captured_payment(order) is True


def test_initiate_external_at_terminal_creates_captured_intent():
    order = _order(
        "ORD-EXT-POS",
        payment={
            "method": "external",
            "collection": "terminal",
            "amount_q": 5000,
            "tenders": [{"method": "external", "amount_q": 5000, "collection": "terminal", "status": "received"}],
        },
    )

    payment_service.initiate(order)

    intent = _intents(order.ref).get()
    assert intent.method == PaymentIntent.Method.EXTERNAL
    assert intent.status == PaymentIntent.Status.CAPTURED
    assert intent.gateway == ""


def test_initiate_cash_at_terminal_is_idempotent():
    order = _order(
        "ORD-CASH-IDEM",
        payment={"method": "cash", "collection": "terminal", "amount_q": 5000},
    )

    payment_service.initiate(order)
    payment_service.initiate(order)
    order.refresh_from_db()
    ref = order.data["payment"]["intent_ref"]

    # Sem ``intent_ref`` no data (crash entre o settle e o save): reaproveita o capturado.
    order.data["payment"].pop("intent_ref")
    order.save(update_fields=["data"])
    payment_service.initiate(order)

    order.refresh_from_db()
    assert order.data["payment"]["intent_ref"] == ref
    assert _intents(order.ref).count() == 1
    assert PaymentService.captured_total(ref) == 5000


def test_initiate_cash_at_terminal_sums_only_terminal_tenders_of_the_method():
    """Dois tenders em dinheiro no terminal somam num intent; a linha da entrega fica de fora."""
    order = _order(
        "ORD-CASH-2T",
        total_q=6000,
        payment={
            "method": "cash",
            "collection": "terminal",
            "amount_q": 6000,
            "tenders": [
                {"method": "cash", "amount_q": 2000, "collection": "terminal", "status": "received"},
                {"method": "cash", "amount_q": 4000, "collection": "terminal", "status": "received"},
            ],
        },
    )

    payment_service.initiate(order)

    assert _intents(order.ref).get().amount_q == 6000


def test_initiate_cash_at_terminal_skips_cancelled_order():
    order = _order(
        "ORD-CASH-DEAD",
        status=Order.Status.CANCELLED,
        payment={"method": "cash", "collection": "terminal", "amount_q": 5000},
    )

    payment_service.initiate(order)

    assert not _intents(order.ref).exists()


# ── refund: dinheiro estorna no Payman ──────────────────────────────────────


@_MOCK_ADAPTERS
def test_refund_leaves_cash_alone_because_cancelling_is_not_handing_money_back():
    """Cancelar não é devolver. O estorno automático do cancel não toca em
    dinheiro: às 22h o gestor cancela e ninguém abriu gaveta. O intent fica
    capturado e o pedido cancelado vira devolução pendente."""
    order = _order("ORD-CASH-REFUND", payment={"method": "cash", "collection": "terminal", "amount_q": 5000})
    payment_service.initiate(order)
    order.refresh_from_db()
    ref = order.data["payment"]["intent_ref"]
    order.status = Order.Status.CANCELLED
    order.save(update_fields=["status"])

    payment_service.refund(order)

    intent = PaymentService.get(ref)
    assert intent.status == PaymentIntent.Status.CAPTURED
    assert not intent.transactions.filter(type=PaymentTransaction.Type.REFUND).exists()
    pending = payment_service.pending_cash_refunds()
    assert [(p.order_ref, p.amount_q, p.intent_refs) for p in pending] == [("ORD-CASH-REFUND", 5000, (ref,))]


@_MOCK_ADAPTERS
def test_refund_cash_hands_money_back_from_an_open_shift_in_both_books():
    """A devolução é o gesto físico: turno aberto, Payman e livro na mesma transação; repetir não dobra."""
    from django.contrib.auth import get_user_model
    from shopman.cashman import Entry
    from shopman.cashman import services as cash

    order = _order("ORD-CASH-HANDBACK", payment={"method": "cash", "collection": "terminal", "amount_q": 5000})
    payment_service.initiate(order)
    order.refresh_from_db()
    ref = order.data["payment"]["intent_ref"]
    order.status = Order.Status.CANCELLED
    order.save(update_fields=["status"])
    operator = get_user_model().objects.create_user(username="marina", password="x")
    shift = cash.open_shift(operator=operator, float_q=10000)

    assert payment_service.refund_cash(order, shift=shift, actor=operator) == 5000
    assert payment_service.refund_cash(order, shift=shift, actor=operator) == 0

    intent = PaymentService.get(ref)
    assert intent.status == PaymentIntent.Status.REFUNDED
    assert PaymentService.refunded_total(ref) == 5000
    assert intent.transactions.filter(type=PaymentTransaction.Type.REFUND).count() == 1
    (line,) = Entry.objects.filter(kind=Entry.Kind.REFUND)
    assert line.amount_q == -5000 and line.order_ref == order.ref and line.payment_ref == ref
    assert cash.balance(shift) == 5000
    assert payment_service.pending_cash_refunds() == []


def test_refund_cash_requires_an_open_shift():
    from django.contrib.auth import get_user_model

    order = _order("ORD-CASH-NOSHIFT", payment={"method": "cash", "collection": "terminal", "amount_q": 5000})
    payment_service.initiate(order)
    operator = get_user_model().objects.create_user(username="marina", password="x")
    with pytest.raises(ValueError, match="Abra o caixa"):
        payment_service.refund_cash(order, shift=None, actor=operator)


def test_refund_without_intent_is_still_a_noop():
    """COD por acertar / loja online em dinheiro: nada capturado, nada a estornar."""
    order = _order("ORD-CASH-NOINTENT", payment={"method": "cash"}, channel_ref="web")

    payment_service.refund(order)

    assert not PaymentTransaction.objects.filter(intent__order_ref=order.ref).exists()


# ── PDV: o intent nasce no fechamento da venda, com o total selado ──────────


class _PosSale:
    """Venda direta no PDV (sem comanda), com catálogo mínimo e um turno de caixa aberto.

    A venda do terminal acontece DENTRO de um turno do ``cashman`` (a linha
    ``sale`` nasce no livro dele); o ``cash_shift_id`` vem do servidor, como
    faz o backstage.
    """

    def __init__(self):
        from django.contrib.auth import get_user_model
        from shopman.cashman import services as cash
        from shopman.offerman.models import Product

        self.operator = get_user_model().objects.create_user(username="cash-operator", password="x")
        self.shift = cash.open_shift(operator=self.operator, float_q=10000)
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
        Product.objects.create(
            sku="POS-CASH-ITEM",
            name="Item de balcão",
            base_price_q=1200,
            is_published=True,
            is_sellable=True,
        )

    def close(self, *, client_request_id: str, **overrides):
        payload = {
            "items": [{"sku": "POS-CASH-ITEM", "name": "Item de balcão", "qty": 1, "unit_price_q": 1200}],
            "customer_name": "Cliente PDV",
            "payment_method": "cash",
            "client_request_id": client_request_id,
            "cash_shift_id": self.shift.pk,
        }
        payload.update(overrides)
        return pos_service.close_sale(
            channel_ref="pdv",
            payload=payload,
            actor="pos:cash-operator",
            operator_username="cash-operator",
        )


@pytest.fixture
def pos_sale():
    return _PosSale()


def test_pos_cash_sale_with_change_settles_the_tender_not_the_bill(pos_sale):
    """Cliente entrega R$ 20,00 por R$ 12,00: o intent vale R$ 12,00 e o troco fica no pedido."""
    result = pos_sale.close(
        client_request_id="pos:cash-change",
        payment_tenders=[{"method": "cash", "amount_q": 2000, "collection": "terminal"}],
        tendered_amount_q=2000,
    )

    order = Order.objects.get(ref=result.order_ref)
    payment = order.data["payment"]
    intent = _intents(order.ref).get()
    assert payment["method"] == "cash"
    assert payment["intent_ref"] == intent.ref
    assert payment["tenders"][0]["amount_q"] == 1200
    assert payment["change_q"] == 800
    assert intent.amount_q == 1200 == order.total_q
    assert intent.status == PaymentIntent.Status.CAPTURED
    assert intent.gateway == ""
    # O PDV não tem nada a exibir para dinheiro (nem QR nem URL).
    assert result.payment == {}


def test_pos_cash_sale_repeat_request_keeps_single_intent(pos_sale):
    first = pos_sale.close(client_request_id="pos:cash-idem", tendered_amount_q=1200)
    second = pos_sale.close(client_request_id="pos:cash-idem", tendered_amount_q=1200)

    assert second.order_ref == first.order_ref
    assert _intents(first.order_ref).count() == 1


def test_pos_mixed_sale_settles_one_intent_per_method(pos_sale):
    """Venda mista: um intent por método, cada tender aponta o seu; sem ``intent_ref`` no topo."""
    result = pos_sale.close(
        client_request_id="pos:cash-mixed",
        payment_tenders=[
            {"method": "cash", "amount_q": 500, "collection": "terminal"},
            {"method": "external", "amount_q": 700, "collection": "terminal"},
        ],
    )

    order = Order.objects.get(ref=result.order_ref)
    payment = order.data["payment"]
    assert payment["method"] == "mixed"
    assert "intent_ref" not in payment
    by_method = {i.method: i for i in _intents(order.ref)}
    assert set(by_method) == {"cash", "external"}
    assert by_method["cash"].amount_q == 500 and by_method["external"].amount_q == 700
    assert all(i.status == PaymentIntent.Status.CAPTURED for i in by_method.values())
    assert payment["tenders"][0]["intent_ref"] == by_method["cash"].ref
    assert payment["tenders"][1]["intent_ref"] == by_method["external"].ref


def test_pos_cash_on_delivery_does_not_settle(pos_sale):
    """Entrega paga em dinheiro na porta: nada capturado até o acerto."""
    result = pos_sale.close(
        client_request_id="pos:cash-cod",
        fulfillment_type="delivery",
        payment_collection="on_delivery",
        delivery_address="Rua das Flores, 1",
        customer_phone="+5543999990001",
    )

    order = Order.objects.get(ref=result.order_ref)
    assert order.data["payment"]["collection"] == "on_delivery"
    assert "intent_ref" not in order.data["payment"]
    assert not _intents(order.ref).exists()


@_MOCK_ADAPTERS
def test_pos_cancel_of_cash_sale_refunds_in_payman(pos_sale, django_capture_on_commit_callbacks):
    """Cancelar a venda em dinheiro grava o estorno no Payman (o ``on_cancelled`` roda o refund)."""
    result = pos_sale.close(client_request_id="pos:cash-cancel", tendered_amount_q=1200)
    order = Order.objects.get(ref=result.order_ref)
    ref = order.data["payment"]["intent_ref"]

    with django_capture_on_commit_callbacks(execute=True):
        pos_service.cancel_recent_order(order_ref=order.ref, actor="pos:cash-operator")

    order.refresh_from_db()
    intent = PaymentService.get(ref)
    assert order.status == Order.Status.CANCELLED
    assert intent.status == PaymentIntent.Status.REFUNDED
    assert intent.transactions.filter(type=PaymentTransaction.Type.REFUND, amount_q=1200).count() == 1
    assert PaymentService.captured_total(ref) - PaymentService.refunded_total(ref) == 0
