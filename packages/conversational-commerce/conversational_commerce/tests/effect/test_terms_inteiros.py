"""Os termos apresentados são o documento canônico inteiro (v2 4.7), e a resposta diz o estado de agora.

- o fato dos termos leva itens, ajustes, recebimento e condições, nunca o destinatário (dado pessoal);
- o nome de cada item vem do fato do item (``item.<ref>``), nunca de quem formata;
- depois do recibo de sucesso do ``change_cart``, o carrinho é cotado de novo, e o sujeito é relido
  (o efeito pode ter criado o carrinho);
- depois do ``commit_order``, o pedido é lido pela porta, e o total sai dele.
"""

from __future__ import annotations

from conversational_commerce.engine.state import Subject
from conversational_commerce.engine.turn import terms_fact
from conversational_commerce.testing.journeys import j4, run_journey

from .helpers import CTX, engine


def test_the_terms_fact_is_the_sealed_document_without_the_recipient():
    turn_engine, world = engine()
    terms = world.commerce_read.quote(CTX, "cart-1")
    fact = terms_fact(terms, {"ITEM-A": "Item A"})
    assert "recipient" not in fact and "subject_ref" not in str(fact)
    assert fact["items"] == [{"ref": "ITEM-A", "quantity": "2", "unit": terms.items[0].quantity.unit,
                              "unit_price": {"price_minor": terms.items[0].unit_price.amount_minor, "currency": "XTS"},
                              "line_total": {"price_minor": terms.items[0].line_total.amount_minor, "currency": "XTS"},
                              "name": "Item A"}]
    assert fact["total"] == {"price_minor": terms.total.amount_minor, "currency": "XTS"}
    assert fact["fulfillment"] == {"mode": "pickup"} and fact["conditions"] == {} and fact["adjustments"] == []


def test_a_name_the_item_fact_does_not_give_is_left_out():
    turn_engine, world = engine()
    fact = terms_fact(world.commerce_read.quote(CTX, "cart-1"), {})
    assert "name" not in fact["items"][0]  # o formatador mostra a referência, nunca inventa o nome


def test_the_cart_reply_is_the_cart_quoted_after_the_change_with_the_item_name():
    turn_engine, world = engine()
    [changed] = run_journey(turn_engine, CTX, [j4.CHANGE])
    assert changed.problems == ()
    assert changed.result.text == "Done. Your cart now has:\n3 × Item A: XTS 13.50\nTotal: XTS 13.50."
    backings = {claim.backing for claim in changed.result.reply.plan.parts[0].claims}
    assert backings == {"receipt", "fact"}  # o efeito pelo recibo, a sacola pelos termos novos


def test_the_subject_is_read_again_after_the_change():
    """O carrinho que o efeito criou é o que se cota (o adaptador diz qual é, depois do efeito)."""
    box = {"cart": "cart-new"}
    turn_engine, world = engine()
    world.state.carts["cart-new"] = {}
    world.state.cart_owner["cart-new"] = "customer-1"
    turn_engine.subject_of = lambda ctx, event: Subject(subject_ref=ctx.subject, identity_evidence=(j4.VERIFIED,),
                                                       cart_ref=box["cart"])
    original = world.commerce_execute._apply

    def apply(command):
        ref = original(command)
        box["cart"] = "cart-1"  # o sistema de registro diz que o carrinho de verdade é este
        return ref

    world.commerce_execute._apply = apply
    [changed] = run_journey(turn_engine, CTX, [j4.CHANGE])
    refs = {claim.ref for claim in changed.result.reply.plan.parts[0].claims if claim.backing == "fact"}
    assert refs == {"terms.cart-1"}


def test_the_order_reply_says_the_total_of_the_order_read_after_the_effect():
    turn_engine, world = engine()
    results = run_journey(turn_engine, CTX, j4.STEPS)
    placed = results[-1].result
    assert placed.text == "Your order order-0001 is placed. Total: XTS 13.50. Track it: order-0001."
    claims = {(claim.slot, claim.backing, claim.ref) for claim in placed.reply.plan.parts[0].claims}
    assert ("total", "fact", "order.order-0001") in claims
