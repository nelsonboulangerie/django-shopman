"""A forma de pagamento: condição obrigatória dos termos e mudança material do carrinho (#3382, básico).

- Faltando a condição, o ``present_terms`` não apresenta os termos: pergunta, com as opções do canal
  (``commerce_read.requirements``), e nenhuma pergunta de confirmação nasce.
- ``choose_payment`` → ``set_payment`` (A2): a forma tem de ser uma das do canal; o efeito sobe a versão
  do carrinho, e por isso a escolha depois do resumo invalida o "sim" aos termos de antes.
- Escolhida a forma, o "pode fechar" apresenta os termos com ela nas condições.
"""

from __future__ import annotations

from conversational_commerce.testing.fakes import FakeWorld
from conversational_commerce.testing.journeys import j4, run_journey
from conversational_commerce.testing.journeys.runner import JourneyStep

from .helpers import CTX, engine


def _world():
    world = FakeWorld()
    world.state.payment_methods = ("pix", "card")  # duas formas: escolher é obrigatório
    return world


def _step(mid, *acts, advance=30):
    return JourneyStep(message=j4.message(mid, mid), understanding={"acts": list(acts)},
                       expect_moves=(), expect_text=(), advance_seconds=advance)


CLOSE = _step("close", {"act": "place_order"})
PIX = _step("pix", {"act": "choose_payment", "fields": {"method": "pix"}})
YES = _step("yes", {"act": "affirm"})


def test_without_a_payment_method_the_summary_asks_with_the_channel_options_and_no_offer():
    turn_engine, world = engine(steps=(CLOSE,), world=_world())
    result = turn_engine.turn(CTX, CLOSE.message)
    assert result.reply.template_ids == ("present_terms.needs_payment_method",)
    assert result.text == "How would you like to pay? pix, card"
    assert result.episode.state != "waiting_authorization"  # nenhuma pergunta de confirmação no ar


def test_choosing_then_closing_presents_the_terms_with_the_payment_and_yes_places_them():
    steps = (PIX, CLOSE, YES)
    turn_engine, world = engine(steps=steps, world=_world())
    chose, close, yes = (r.result for r in run_journey(turn_engine, CTX, list(steps)))
    assert [c.action for c in chose.commands] == ["set_payment"] and world.state.payment["cart-1"] == "pix"
    assert chose.text.startswith("Done: payment by pix.")
    assert close.reply.template_ids == ("present_terms.confirm",) and "payment_method: pix" in close.text
    assert [c.action for c in yes.commands] == ["commit_order"] and len(world.state.orders) == 1


def test_a_method_the_channel_does_not_offer_is_ineligible():
    cash = _step("cash", {"act": "choose_payment", "fields": {"method": "cash"}})
    turn_engine, world = engine(steps=(cash,), world=_world())
    result = turn_engine.turn(CTX, cash.message)
    assert result.commands == () and "cart-1" not in world.state.payment
    blocked = [c for c in result.decisions[0].candidates if c.move == "set_payment"]
    assert blocked and "payment_method_not_offered" in blocked[0].blocked_by


def test_changing_the_payment_after_the_summary_never_confirms_the_old_terms():
    world = _world()
    world.state.payment["cart-1"] = "card"
    card_summary, pix_now = CLOSE, _step("pix-now", {"act": "affirm"}, {"act": "choose_payment",
                                                                         "fields": {"method": "pix"}})
    turn_engine, world = engine(steps=(card_summary, pix_now, YES), world=world)
    close, both, yes = (r.result for r in run_journey(turn_engine, CTX, [card_summary, pix_now, YES]))
    assert "payment_method: card" in close.text
    assert [c.action for c in both.commands] == ["set_payment"]  # o "sim" de antes não grava (propriedade 2)
    assert both.reply.template_ids == ("present_terms.confirm",)
    assert not any(c.action == "commit_order" for c in both.commands)
    assert "payment_method: pix" in both.text  # os termos novos, apresentados
    assert [c.action for c in yes.commands] == ["commit_order"] and len(world.state.orders) == 1
    order = next(iter(world.state.orders.values()))
    assert order["terms_hash"] == yes.commands[0].terms_hash


def test_cart_and_payment_in_one_turn_run_in_sequence():
    both = _step("both", {"act": "change_quantity", "fields": {"item": "ITEM-A", "quantity": "3"}},
                 {"act": "choose_payment", "fields": {"method": "pix"}}, advance=0)
    turn_engine, world = engine(steps=(both,), world=_world())
    result = turn_engine.turn(CTX, both.message)
    assert [c.action for c in result.commands] == ["change_cart", "set_payment"]
    assert world.state.carts["cart-1"]["ITEM-A"] == "3" and world.state.payment["cart-1"] == "pix"


def test_unknown_requirements_hold_the_close_and_never_present_terms():
    """K04: sem saber o que falta, o fechamento não apresenta termos nem nasce pergunta de confirmação."""
    from conversational_commerce.testing.fakes import Fault

    world = _world()
    world.faults.arm("requirements", Fault.SOURCE_FAILED, times=5)
    turn_engine, world = engine(steps=(CLOSE,), world=world)
    result = turn_engine.turn(CTX, CLOSE.message)
    assert "present_terms" not in result.chosen_moves
    blocked = [c for c in result.decisions[0].candidates if c.move == "present_terms"]
    assert blocked and "fact_unavailable" in blocked[0].blocked_by
    assert result.episode.state != "waiting_authorization"


def test_unknown_requirements_refuse_the_choice_as_unavailable_not_as_not_offered():
    from conversational_commerce.testing.fakes import Fault

    world = _world()
    world.faults.arm("requirements", Fault.SOURCE_FAILED, times=5)
    turn_engine, world = engine(steps=(PIX,), world=world)
    result = turn_engine.turn(CTX, PIX.message)
    assert result.commands == () and "cart-1" not in world.state.payment
    [blocked] = [c for c in result.decisions[0].candidates if c.move == "set_payment"]
    assert blocked.blocked_by == ("fact_unavailable",)  # nunca "forma não oferecida": não se sabe


def test_a_payment_without_the_method_is_a_question_not_a_limitation():
    bare = _step("bare", {"act": "choose_payment"})
    turn_engine, world = engine(steps=(bare,), world=_world())
    result = turn_engine.turn(CTX, bare.message)
    assert result.chosen_moves == ["ask_clarification"] and result.commands == ()


def test_a_method_the_channel_does_not_offer_says_so_with_the_options():
    cash = _step("cash", {"act": "choose_payment", "fields": {"method": "cash"}})
    turn_engine, world = engine(steps=(cash,), world=_world())
    result = turn_engine.turn(CTX, cash.message)
    assert result.reply.template_ids == ("set_payment.not_offered",)
    assert result.text == "We don't take that payment method here. How would you like to pay? pix, card"
