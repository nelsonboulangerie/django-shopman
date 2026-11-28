"""O "não" ao resumo ("deixa pra lá"): nada se registra, e a frase diz isso só quando é verdade (#3388).

O ``deny`` que responde à pergunta dos termos já invalida a autorização e não grava nada, sem ato
novo. A frase "nada foi registrado, o carrinho ficou como estava" só sai quando NENHUM efeito foi
escolhido no turno; com uma mudança junto ("deixa pra lá, tira o croissant"), ela seria falsa.
"""

from __future__ import annotations

from conversational_commerce.testing.journeys import j4, run_journey
from conversational_commerce.testing.journeys.runner import JourneyStep

from .helpers import CTX, engine


def _no(*acts):
    step = JourneyStep(message=j4.message("j4-no", "never mind"), understanding={"acts": list(acts)},
                       expect_moves=(), expect_text=(), advance_seconds=30)
    turn_engine, world = engine(steps=(j4.CHANGE, j4.QUOTE, step))
    *_, last = run_journey(turn_engine, CTX, [j4.CHANGE, j4.QUOTE, step])
    return last.result, world


def test_no_to_the_terms_with_no_effect_says_nothing_was_placed():
    result, world = _no({"act": "deny"})
    assert result.reply.template_ids == ("acknowledge.terms_declined",)
    assert result.text == "Understood, nothing was placed. Your cart stays as it is."
    assert world.state.orders == {} and world.state.carts["cart-1"] == {"ITEM-A": "3"}
    assert result.episode.state == "active"  # a autorização foi invalidada


def test_no_to_the_terms_with_a_change_never_says_the_cart_stays():
    remove = {"act": "change_quantity", "fields": {"item": "ITEM-A", "quantity": "0"}}
    result, world = _no({"act": "deny"}, remove)
    assert "acknowledge.terms_declined" not in result.reply.template_ids
    assert "stays as it is" not in (result.text or "")
    assert world.state.orders == {}


def test_a_no_to_another_question_is_still_got_it():
    step = JourneyStep(message=j4.message("j4-plain-no", "no"), understanding={"acts": [{"act": "deny"}]},
                       expect_moves=(), expect_text=())
    turn_engine, _ = engine(steps=(step,))
    result = turn_engine.turn(CTX, step.message)
    assert "acknowledge.terms_declined" not in result.reply.template_ids
