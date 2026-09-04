"""Mercadoria não sai sem o dinheiro entrar — e dinheiro na porta continua saindo.

Havia quatro portas por onde a sacola saía sem um centavo capturado:

1. o ``advance_block`` do Gestor só perguntava sobre pagamento em ``ACCEPTED``,
   então ``PREPARING → READY → DISPATCHED`` passava à mão sem consulta nenhuma;
2. o gate do operador não conhecia o ``link`` (só ``pix``/``card``), embora o
   lifecycle já soubesse que link é cobrança remota;
3. a expedição do KDS — o painel por onde a mercadoria FISICAMENTE sai — chamava
   ``transition_status`` direto, sem régua de pagamento alguma;
4. nada no código distinguia "não pago porque é dinheiro na porta" de "não pago
   porque o link venceu".

O quarto item é o que segura os outros três: fechar o gate sem essa distinção
quebraria a operação legítima de dinheiro na porta, que por desenho NUNCA tem
captura antes da entrega. É por isso que o primeiro teste deste arquivo é o do
COD despachando — ele é o guarda-corpo da correção, não um caso de borda.
"""

from __future__ import annotations

import pytest
from django.core.cache import cache
from shopman.orderman.models import Order

from shopman.shop.services import kds, operator_orders, payment_gate

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _gate_channel():
    """Canal de balcão (``payment.timing == "external"``) — o pior caso do gate.

    É justamente onde o guard do lifecycle se cala: se a régua nova dependesse do
    ``timing`` do canal, o link do PDV continuaria passando.
    """
    from shopman.shop.models import Channel

    Channel.objects.create(
        ref="gate-pdv",
        name="Balcão (gate)",
        config={
            "confirmation": {"mode": "immediate"},
            "payment": {"method": ["cash", "pix", "link"], "timing": "external"},
        },
    )
    cache.clear()
    yield
    cache.clear()


def _order(ref, *, status, payment, fulfillment_type="delivery", captured=False):
    order = Order.objects.create(
        ref=ref,
        channel_ref="gate-pdv",
        session_key=f"SESS-{ref}",
        status=status,
        total_q=3200,
        data={"fulfillment_type": fulfillment_type, "payment": dict(payment)},
    )
    method = payment.get("method") or "cash"
    if method in payment_gate.UPFRONT_DIGITAL_PAYMENT_METHODS:
        from shopman.payman import PaymentService

        intent = PaymentService.create_intent(
            order_ref=order.ref, amount_q=order.total_q, method="pix"
        )
        order.data["payment"]["intent_ref"] = intent.ref
        order.save(update_fields=["data"])
        if captured:
            PaymentService.authorize(intent.ref, gateway_id=f"gw-{ref}")
            PaymentService.capture(intent.ref)
    return order


def _cod(ref="COD-1", *, status=Order.Status.READY):
    """Dinheiro na entrega, como o PDV grava: o dinheiro chega na porta."""
    return _order(ref, status=status, payment={"method": "cash", "collection": "on_delivery"})


def _unpaid_link(ref="LINK-1", *, status=Order.Status.READY, fulfillment_type="delivery"):
    return _order(
        ref, status=status, payment={"method": "link"}, fulfillment_type=fulfillment_type
    )


def _unpaid_pix(ref="PIX-1", *, status=Order.Status.READY):
    return _order(ref, status=status, payment={"method": "pix"})


def _paid_pix(ref="PIX-OK", *, status=Order.Status.READY):
    return _order(ref, status=status, payment={"method": "pix"}, captured=True)


# ── (a) COD continua despachando ───────────────────────────────────────────
# O teste que impede a correção de quebrar o balcão.


def test_cash_on_delivery_dispatches_in_the_manager():
    order = _cod("COD-GESTOR")

    assert payment_gate.collects_on_delivery(order) is True
    assert operator_orders.advance_block(order) == operator_orders.AdvanceBlock.NONE

    operator_orders.advance_order(order, actor="operator:test")
    order.refresh_from_db()
    assert order.status == Order.Status.DISPATCHED


def test_cash_on_delivery_dispatches_from_the_expedition_board():
    order = _cod("COD-KDS")

    assert kds.expedition_block_reason(order, action="dispatch") == ""

    kds.expedition_action(order, action="dispatch", actor="operator:test")
    order.refresh_from_db()
    assert order.status == Order.Status.DISPATCHED


def test_cash_on_delivery_also_starts_prep():
    """O gate cobre ``ACCEPTED → PREPARING``, e o COD passa lá também."""
    order = _cod("COD-PREP", status=Order.Status.ACCEPTED)

    assert operator_orders.advance_block(order) == operator_orders.AdvanceBlock.NONE
    operator_orders.advance_order(order, actor="operator:test")
    order.refresh_from_db()
    assert order.status == Order.Status.PREPARING


def test_storefront_cash_delivery_is_read_as_cash_on_delivery():
    """Pedido antigo da loja online: dinheiro + entrega, sem a marca ``collection``.

    Sem o fallback por natureza, ele seria lido como "não pagou" e o Gestor
    barraria uma entrega perfeitamente legítima.
    """
    order = _order("LOJA-COD", status=Order.Status.READY, payment={"method": "cash"})

    assert payment_gate.collects_on_delivery(order) is True
    assert operator_orders.advance_block(order) == operator_orders.AdvanceBlock.NONE


# ── (b) link não capturado é barrado nos DOIS caminhos ─────────────────────


def test_unpaid_link_is_blocked_in_the_manager():
    order = _unpaid_link("LINK-GESTOR")

    assert (
        operator_orders.advance_block(order) == operator_orders.AdvanceBlock.PAYMENT_NOT_CAPTURED
    )
    with pytest.raises(ValueError):
        operator_orders.advance_order(order, actor="operator:test")
    order.refresh_from_db()
    assert order.status == Order.Status.READY


def test_unpaid_link_is_blocked_in_the_expedition():
    order = _unpaid_link("LINK-KDS")

    assert kds.expedition_block_reason(order, action="dispatch") != ""
    with pytest.raises(ValueError):
        kds.expedition_action(order, action="dispatch", actor="operator:test")
    order.refresh_from_db()
    assert order.status == Order.Status.READY


def test_unpaid_link_pickup_is_blocked_at_the_counter_handoff():
    """Retirada: a saída é ``READY → COMPLETED``, e ela também é entrega de bem."""
    order = _unpaid_link("LINK-BALCAO", fulfillment_type="pickup")

    assert (
        operator_orders.advance_block(order) == operator_orders.AdvanceBlock.PAYMENT_NOT_CAPTURED
    )
    with pytest.raises(ValueError):
        kds.expedition_action(order, action="complete", actor="operator:test")
    order.refresh_from_db()
    assert order.status == Order.Status.READY


# ── (c) pix não capturado, idem ────────────────────────────────────────────


def test_unpaid_pix_is_blocked_in_the_manager():
    order = _unpaid_pix("PIX-GESTOR")

    assert (
        operator_orders.advance_block(order) == operator_orders.AdvanceBlock.PAYMENT_NOT_CAPTURED
    )
    with pytest.raises(ValueError):
        operator_orders.advance_order(order, actor="operator:test")


def test_unpaid_pix_is_blocked_in_the_expedition():
    order = _unpaid_pix("PIX-KDS")

    with pytest.raises(ValueError):
        kds.expedition_action(order, action="dispatch", actor="operator:test")
    order.refresh_from_db()
    assert order.status == Order.Status.READY


# ── (d) pedido pago avança normalmente ─────────────────────────────────────


def test_paid_order_advances_in_the_manager():
    order = _paid_pix("PIX-OK-GESTOR")

    assert operator_orders.advance_block(order) == operator_orders.AdvanceBlock.NONE
    operator_orders.advance_order(order, actor="operator:test")
    order.refresh_from_db()
    assert order.status == Order.Status.DISPATCHED


def test_paid_order_advances_in_the_expedition():
    order = _paid_pix("PIX-OK-KDS")

    assert kds.expedition_block_reason(order, action="dispatch") == ""
    kds.expedition_action(order, action="dispatch", actor="operator:test")
    order.refresh_from_db()
    assert order.status == Order.Status.DISPATCHED


# ── (e) a régua é a MESMA nos dois caminhos ────────────────────────────────


@pytest.mark.parametrize(
    "make, action",
    [
        (_cod, "dispatch"),
        (_unpaid_link, "dispatch"),
        (_unpaid_pix, "dispatch"),
        (_paid_pix, "dispatch"),
    ],
)
def test_manager_and_expedition_answer_the_same(make, action):
    order = make()

    bloqueio = operator_orders.advance_block(order)
    gestor = operator_orders.advance_block_message(bloqueio)
    expedicao = kds.expedition_block_reason(order, action=action)

    # Mesmo veredito E mesma frase: duas réguas foi exatamente o problema.
    assert bool(gestor) == bool(expedicao)
    assert gestor == expedicao


# ── O gate não é mais "só em ACCEPTED" ─────────────────────────────────────


def test_the_gate_covers_every_step_that_hands_over_goods():
    """``ACCEPTED`` e ``READY`` barram; ``PREPARING → READY`` passa, de propósito.

    Marcar "pronto" não entrega nada ao cliente — o trabalho já foi feito e a
    sacola continua na casa. Barrar ali só encalharia um card na cozinha; quem
    segura a mercadoria é o degrau seguinte, que está barrado.
    """
    aceito = _unpaid_link("LINK-ACEITO", status=Order.Status.ACCEPTED)
    em_preparo = _unpaid_link("LINK-PREPARO", status=Order.Status.PREPARING)
    pronto = _unpaid_link("LINK-PRONTO", status=Order.Status.READY)

    assert (
        operator_orders.advance_block(aceito) == operator_orders.AdvanceBlock.PAYMENT_NOT_CAPTURED
    )
    assert operator_orders.advance_block(em_preparo) == operator_orders.AdvanceBlock.NONE
    assert (
        operator_orders.advance_block(pronto) == operator_orders.AdvanceBlock.PAYMENT_NOT_CAPTURED
    )


def test_an_order_with_no_payment_info_is_not_gated():
    """Ausência de dado não é inadimplência: barrar aqui trava legado sem ganho."""
    order = Order.objects.create(
        ref="SEM-PAGAMENTO",
        channel_ref="gate-pdv",
        session_key="SESS-SEM",
        status=Order.Status.READY,
        total_q=1000,
        data={"fulfillment_type": "pickup"},
    )

    assert operator_orders.advance_block(order) == operator_orders.AdvanceBlock.NONE


def test_a_live_intent_without_a_method_is_treated_as_gateway_money():
    """Só dinheiro de gateway nasce com intent sem ninguém dizer a forma."""
    order = Order.objects.create(
        ref="INTENT-SEM-METODO",
        channel_ref="gate-pdv",
        session_key="SESS-INT",
        status=Order.Status.READY,
        total_q=1000,
        data={"fulfillment_type": "pickup", "payment": {"intent_ref": "int-orfao"}},
    )

    assert (
        operator_orders.advance_block(order) == operator_orders.AdvanceBlock.PAYMENT_NOT_CAPTURED
    )


def test_delivered_to_completed_is_bookkeeping_not_a_handover():
    """A mercadoria já saiu: barrar a escrituração não recupera nada."""
    order = _unpaid_link("LINK-ENTREGUE", status=Order.Status.DELIVERED)

    assert payment_gate.transition_hands_over_goods(
        Order.Status.DELIVERED, Order.Status.COMPLETED
    ) is False
    assert operator_orders.advance_block(order) == operator_orders.AdvanceBlock.NONE
