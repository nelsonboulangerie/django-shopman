"""O quando antes dos termos (#3482): o dia, retirar ou entregar, e o horário, na ordem do fechamento.

Sem isso, os termos se apresentavam sem o que o sistema de registro exige para gravar ("Posso registrar?" de
um pedido sem dia nem horário), e o "sim" do cliente não fechava nada.
"""

from __future__ import annotations

from conversational_commerce.testing.fakes import FakeWorld
from conversational_commerce.testing.journeys import j4, run_journey
from conversational_commerce.testing.journeys.runner import JourneyStep

from .helpers import CTX, engine


def _step(mid, *acts, text=None):
    return JourneyStep(message=j4.message(mid, text or mid), understanding={"acts": list(acts)},
                       expect_moves=(), expect_text=(), advance_seconds=30)


CLOSE = _step("close", {"act": "place_order"})
TOMORROW = _step("tomorrow", {"act": "choose_fulfillment", "fields": {"date": "2026-01-06"}})
PICKUP = _step("pickup", {"act": "choose_fulfillment", "fields": {"mode": "pickup"}})
AT_FOUR = _step("four", {"act": "choose_fulfillment", "fields": {"time": "16:00"}})
YES = _step("yes", {"act": "affirm"})


def _world():
    world = FakeWorld()
    world.state.payment_methods = ("card",)
    world.state.pickup_slots = ("9h às 12h", "15h às 18h")
    return world


def test_the_close_asks_the_day_then_the_mode_then_the_time_and_only_then_presents_the_terms():
    steps = (CLOSE, TOMORROW, PICKUP, AT_FOUR, YES)
    turn_engine, world = engine(steps=steps, world=_world())
    close, day, mode, time, yes = (r.result for r in run_journey(turn_engine, CTX, list(steps)))
    assert close.reply.template_ids == ("present_terms.needs_fulfillment_date",)
    assert day.reply.template_ids[-1] == "present_terms.needs_fulfillment_type"  # a resposta volta aos termos
    assert mode.reply.template_ids[-1] == "present_terms.needs_delivery_time_slot"
    assert "9h às 12h" in mode.text and "15h às 18h" in mode.text  # os horários do fato
    assert time.reply.template_ids[-1] == "present_terms.confirm"  # só agora os termos
    assert [c.action for c in yes.commands] == ["commit_order"]
    assert world.state.fulfillment["cart-1"] == {"date": "2026-01-06", "mode": "pickup", "time": "16:00"}


def test_what_was_said_with_the_order_is_not_asked_again():
    said = _step("all", {"act": "choose_fulfillment", "fields": {"date": "2026-01-06", "mode": "pickup",
                                                                 "time": "16:00"}})
    steps = (said, CLOSE)
    turn_engine, world = engine(steps=steps, world=_world())
    _said, close = (r.result for r in run_journey(turn_engine, CTX, list(steps)))
    assert close.reply.template_ids == ("present_terms.confirm",)


def test_without_pickup_slots_the_fake_channel_does_not_ask_the_when():
    world = FakeWorld()
    world.state.payment_methods = ("card",)
    turn_engine, world = engine(steps=(CLOSE,), world=world)
    assert turn_engine.turn(CTX, CLOSE.message).reply.template_ids == ("present_terms.confirm",)


def test_a_cart_change_while_the_close_asks_says_it_changed_and_keeps_the_question():
    """#3488: "na verdade 3" com o fechamento perguntando o dia muda a sacola, diz que mudou e repete a pergunta
    aberta. Antes, só a pergunta voltava, como se nada tivesse acontecido."""
    three = _step("three", {"act": "change_quantity", "fields": {"item": "ITEM-A", "quantity": "3"}})
    steps = (CLOSE, three)
    turn_engine, world = engine(steps=steps, world=_world())
    _close, changed = (r.result for r in run_journey(turn_engine, CTX, list(steps)))
    assert changed.reply.template_ids == ("change_cart.done_total", "present_terms.needs_fulfillment_date")
    assert "Total:" in changed.text
    assert changed.reply.verification.result != "hold"


def test_the_summary_already_shows_the_cart_so_no_extra_part():
    said = _step("all", {"act": "choose_fulfillment", "fields": {"date": "2026-01-06", "mode": "pickup",
                                                                 "time": "16:00"}})
    three = _step("three", {"act": "change_quantity", "fields": {"item": "ITEM-A", "quantity": "3"}})
    steps = (said, CLOSE, three)
    turn_engine, world = engine(steps=steps, world=_world())
    *_, changed = (r.result for r in run_journey(turn_engine, CTX, list(steps)))
    assert changed.reply.template_ids == ("present_terms.confirm",)


def test_the_delivery_asks_the_window_after_the_address():
    """A entrega também tem horário: depois do endereço completo, a janela do dia; só então os termos."""
    delivery = _step("delivery", {"act": "choose_fulfillment", "fields": {"mode": "delivery"}})
    address = _step("addr", {"act": "give_address"}, text="Rua das Flores 120")
    at_three = _step("three-pm", {"act": "choose_fulfillment", "fields": {"time": "15:00"}})
    world = _world()
    world.state.delivery_windows = ("das 9h às 12h", "das 15h às 18h")
    steps = (CLOSE, TOMORROW, delivery, address, at_three)
    turn_engine, world = engine(steps=steps, world=world)
    *_, mode, addr, window = (r.result for r in run_journey(turn_engine, CTX, list(steps)))
    assert mode.reply.template_ids[-1] == "present_terms.needs_delivery_address"
    assert addr.reply.template_ids[-1] == "present_terms.needs_delivery_window"
    assert "das 15h às 18h" in addr.text
    assert window.reply.template_ids[-1] == "present_terms.confirm"


def test_what_was_agreed_comes_before_the_cart_summary_in_the_same_turn():
    """Ensaio no ar (24/11), cartão 1: "2 croissants para retirar amanhã às 16h" respondia o resumo da sacola (que a
    casa termina com o convite "Quer mais alguma coisa?") e SÓ DEPOIS o combinado. O combinado vem antes do resumo."""
    said = _step("all", {"act": "change_quantity", "fields": {"item": "ITEM-A", "quantity": "2"}},
                 {"act": "choose_fulfillment", "fields": {"date": "2026-01-06", "mode": "pickup", "time": "16:00"}})
    turn_engine, _ = engine(steps=(said,), world=_world())
    [result] = (r.result for r in run_journey(turn_engine, CTX, [said]))
    assert result.chosen_moves == ("change_cart", "set_fulfillment")  # a decisão segue a ordem da fala
    assert result.reply.template_ids == ("set_fulfillment.done_time", "change_cart.done")  # a fala, não


def test_the_terms_carry_the_agreed_day_and_window_like_the_record_system():
    """O falso declara nos termos o dia e a janela combinados, como o sistema de registro (o resumo diz o quando)."""
    said = _step("all", {"act": "choose_fulfillment", "fields": {"date": "2026-01-06", "mode": "pickup",
                                                                 "time": "16:00"}})
    steps = (said, CLOSE)
    turn_engine, world = engine(steps=steps, world=_world())
    *_, close = (r.result for r in run_journey(turn_engine, CTX, list(steps)))
    terms = world.commerce_read.quotes[world.state.current_terms["cart-1"]]
    codes = {condition.code: condition.value for condition in terms.conditions}
    assert codes["fulfillment_date"] == "2026-01-06" and codes["fulfillment_window"] == "16:00"
    assert close.reply.template_ids == ("present_terms.confirm",)
