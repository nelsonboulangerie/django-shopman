"""O endereço da entrega pelo motor (cartão 2, #3382), e a volta aos termos depois de uma condição respondida.

- Entrega sem endereço: o fechamento pergunta pelo endereço (``present_terms.needs_delivery_address``),
  antes do pagamento (a ordem recebimento → endereço → sacola → pagamento).
- ``give_address`` não tem campo: o comando leva só a referência protegida da fala, e o sistema de registro
  lê o endereço. O recibo e os termos levam só a referência opaca (P17).
- Leitura com campo de endereço é recusada (``address_not_by_reference``).
- O que falta no endereço é perguntado pelo mesmo mecanismo, com a lista do fato.
- Respondida a condição que o fechamento pediu, o turno volta aos termos sem o cliente repetir "pode fechar".
- O formatador de referência que não resolve SEGURA a mensagem (spec 06).
"""

from __future__ import annotations

from conversational_commerce.engine import Engine, Ports
from conversational_commerce.engine.format import DEFAULT_FORMATTERS
from conversational_commerce.reply import UnresolvedReference
from conversational_commerce.testing.fakes import FakeWorld
from conversational_commerce.testing.journeys import j4, run_journey
from conversational_commerce.testing.journeys.runner import JourneyStep

from .helpers import CTX, engine


def _step(mid, *acts, text=None, advance=30):
    return JourneyStep(message=j4.message(mid, text or mid), understanding={"acts": list(acts)},
                       expect_moves=(), expect_text=(), advance_seconds=advance)


def _delivery_world(methods=("card",)):
    world = FakeWorld()
    world.state.payment_methods = methods
    world.state.fulfillment["cart-1"] = {"mode": "delivery"}
    return world


CLOSE = _step("close", {"act": "place_order"})
ADDRESS = _step("addr", {"act": "give_address"}, text="Rua das Flores 120")
NO_NUMBER = _step("addr-sn", {"act": "give_address"}, text="Rua das Flores")
YES = _step("yes", {"act": "affirm"})


def test_delivery_without_address_asks_for_it_before_anything_else():
    turn_engine, world = engine(steps=(CLOSE,), world=_delivery_world(("pix", "card")))
    result = turn_engine.turn(CTX, CLOSE.message)
    assert result.reply.template_ids == ("present_terms.needs_delivery_address",)
    assert result.episode.state != "waiting_authorization"


def test_the_address_is_read_by_the_system_of_record_and_only_its_reference_travels():
    turn_engine, world = engine(steps=(ADDRESS,), world=_delivery_world())
    result = turn_engine.turn(CTX, ADDRESS.message)
    [command] = result.commands
    assert command.action == "set_delivery_address"
    assert dict(command.parameters) == {"source": "text:Rua das Flores 120"}  # a referência, nunca campo lido
    assert world.state.address["cart-1"]["text"] == "Rua das Flores 120"
    assert result.text.startswith("Done: delivery to addr-cart-1.")  # o neutro do pacote mostra a referência
    assert "Rua das Flores" not in result.text


def test_a_reading_with_address_fields_is_refused():
    leaked = _step("leak", {"act": "give_address", "fields": {"street": "Rua das Flores"}})
    turn_engine, world = engine(steps=(leaked,), world=_delivery_world())
    result = turn_engine.turn(CTX, leaked.message)
    assert result.commands == () and "cart-1" not in world.state.address
    blocked = [c for c in result.decisions[0].candidates if c.move == "set_delivery_address"]
    assert blocked and "address_not_by_reference" in blocked[0].blocked_by


def test_answering_the_address_returns_to_the_terms_without_a_second_close():
    steps = (CLOSE, ADDRESS, YES)
    turn_engine, world = engine(steps=steps, world=_delivery_world())
    close, address, yes = (r.result for r in run_journey(turn_engine, CTX, list(steps)))
    assert close.reply.template_ids == ("present_terms.needs_delivery_address",)
    assert [c.action for c in address.commands] == ["set_delivery_address"]
    assert address.reply.template_ids[-1] == "present_terms.confirm"  # os termos, com o endereço
    assert address.episode.state == "waiting_authorization"
    assert [c.action for c in yes.commands] == ["commit_order"] and len(world.state.orders) == 1


def test_what_is_missing_in_the_address_is_asked_with_the_list_of_the_fact():
    steps = (CLOSE, NO_NUMBER)
    turn_engine, world = engine(steps=steps, world=_delivery_world())
    _close, address = (r.result for r in run_journey(turn_engine, CTX, list(steps)))
    assert address.reply.template_ids[-1] == "present_terms.needs_delivery_address_details"
    assert address.text.endswith("For the delivery, tell me number.")
    assert address.episode.state != "waiting_authorization"


def test_after_the_address_the_payment_is_asked_then_the_terms():
    steps = (CLOSE, ADDRESS, _step("pix", {"act": "choose_payment", "fields": {"method": "pix"}}))
    turn_engine, world = engine(steps=steps, world=_delivery_world(("pix", "card")))
    _close, address, pix = (r.result for r in run_journey(turn_engine, CTX, list(steps)))
    assert address.reply.template_ids[-1] == "present_terms.needs_payment_method"
    assert pix.reply.template_ids[-1] == "present_terms.confirm" and "payment_method: pix" in pix.text


def test_the_payment_answer_returns_to_the_terms_too():
    steps = (CLOSE, _step("pix", {"act": "choose_payment", "fields": {"method": "pix"}}))
    world = FakeWorld()
    world.state.payment_methods = ("pix", "card")
    turn_engine, world = engine(steps=steps, world=world)
    close, pix = (r.result for r in run_journey(turn_engine, CTX, list(steps)))
    assert close.reply.template_ids == ("present_terms.needs_payment_method",)
    assert pix.reply.template_ids[-1] == "present_terms.confirm"


def test_a_change_without_a_pending_close_does_not_present_the_terms():
    pix = _step("pix", {"act": "choose_payment", "fields": {"method": "pix"}})
    world = FakeWorld()
    world.state.payment_methods = ("pix", "card")
    turn_engine, world = engine(steps=(pix,), world=world)
    result = turn_engine.turn(CTX, pix.message)
    assert result.reply.template_ids == ("set_payment.done",)


def test_a_reference_formatter_that_cannot_resolve_holds_the_message():
    def unresolved(value):
        raise UnresolvedReference(value)

    world = _delivery_world()
    turn_engine, _ = engine(steps=(ADDRESS,), world=world)
    held = Engine(turn_engine.ports, turn_engine.profile, subject_of=j4.subject,
                  formatters={**DEFAULT_FORMATTERS, "address": unresolved})
    assert isinstance(held.ports, Ports)
    result = held.turn(CTX, ADDRESS.message)
    assert result.reply.verification.result == "hold"
    assert any(f.code == "reference_unresolved" for f in result.reply.verification.findings)
    assert result.text is None  # nada sai sem o valor


def test_an_address_outside_the_area_says_so_and_asks_again():
    far = _step("far", {"act": "give_address"}, text="far away road 9")
    turn_engine, world = engine(steps=(far,), world=_delivery_world())
    result = turn_engine.turn(CTX, far.message)
    assert result.reply.template_ids == ("set_delivery_address.not_delivered",)
    assert "cart-1" not in world.state.address


def test_an_address_that_cannot_be_located_says_so():
    nowhere = _step("nowhere", {"act": "give_address"}, text="nowhere street")
    turn_engine, world = engine(steps=(nowhere,), world=_delivery_world())
    result = turn_engine.turn(CTX, nowhere.message)
    assert result.reply.template_ids == ("set_delivery_address.not_located",)


def test_an_address_without_delivery_asks_pickup_or_delivery():
    world = FakeWorld()  # retirada: o endereço não tem onde cair, e a pergunta é o modo
    turn_engine, world = engine(steps=(ADDRESS,), world=world)
    result = turn_engine.turn(CTX, ADDRESS.message)
    assert result.reply.template_ids == ("set_delivery_address.ask_mode",) and "cart-1" not in world.state.address


def test_a_no_to_the_pending_close_ends_it_and_a_later_change_does_not_present_the_terms():
    """O "não" encerra o fechamento que pergunta: o "pix" de depois é só a forma, não volta aos termos."""
    no = _step("no", {"act": "deny"})
    pix = _step("pix", {"act": "choose_payment", "fields": {"method": "pix"}})
    world = FakeWorld()
    world.state.payment_methods = ("pix", "card")
    steps = (CLOSE, no, pix)
    turn_engine, world = engine(steps=steps, world=world)
    close, declined, chose = (r.result for r in run_journey(turn_engine, CTX, list(steps)))
    assert close.reply.template_ids == ("present_terms.needs_payment_method",)
    assert declined.reply.template_ids == ("acknowledge.terms_declined",)
    assert chose.reply.template_ids == ("set_payment.done",)  # sem termos: o fechamento acabou


def test_the_pending_close_is_bound_to_the_cart_and_the_epoch():
    from conversational_commerce.engine.turn import CLOSING_KEY, closing_in

    dialogue = {CLOSING_KEY: {"cart": "cart-1", "epoch": 2}}
    assert closing_in(dialogue, "cart-1", 2)
    assert not closing_in(dialogue, "cart-1", 3)  # a conversa mudou de dono: o fechamento não passa
    assert not closing_in(dialogue, "cart-2", 2)
    assert not closing_in({CLOSING_KEY: "cart-1"}, "cart-1", 2)  # forma antiga não vale


# ── o endereço do cadastro: a condição que se responde com sim ou não (#3421) ────────────────────


def _saved_world(*saved, methods=("card",)):
    world = _delivery_world(methods)
    world.state.saved_addresses["cart-1"] = list(saved)
    return world


NO = _step("no", {"act": "deny"})


def test_a_customer_with_a_saved_address_is_offered_it_first():
    turn_engine, world = engine(steps=(CLOSE,), world=_saved_world("Rua do Cadastro 10"))
    result = turn_engine.turn(CTX, CLOSE.message)
    assert result.reply.template_ids == ("present_terms.needs_delivery_address_saved",)
    assert "saved:cart-1:0:" in result.text  # o neutro do pacote mostra a referência; o texto é da casa
    assert "Rua do Cadastro" not in result.text  # P17: o endereço nunca entra pelo motor


def test_more_than_one_saved_address_uses_the_many_template():
    turn_engine, world = engine(steps=(CLOSE,), world=_saved_world("Rua A 1", "Rua B 2"))
    assert turn_engine.turn(CTX, CLOSE.message).reply.template_ids == (
        "present_terms.needs_delivery_address_saved_many",)


def test_yes_to_the_saved_address_takes_it_and_returns_to_the_terms():
    steps = (CLOSE, YES, _step("yes-again", {"act": "affirm"}))
    turn_engine, world = engine(steps=steps, world=_saved_world("Rua do Cadastro 10"))
    close, accepted, placed = (r.result for r in run_journey(turn_engine, CTX, list(steps)))
    [command] = accepted.commands
    assert command.action == "set_delivery_address"
    assert dict(command.parameters) == {"source": "saved:cart-1:0:ruadocadastro10"}
    assert world.state.address["cart-1"]["text"] == "Rua do Cadastro 10"
    assert accepted.reply.template_ids[-1] == "present_terms.confirm"  # o "sim" voltou aos termos
    assert [c.action for c in placed.commands] == ["commit_order"]  # e o "sim" seguinte fecha o pedido


def test_no_to_the_saved_address_asks_for_another_without_ending_the_close():
    steps = (CLOSE, NO, ADDRESS)
    turn_engine, world = engine(steps=steps, world=_saved_world("Rua do Cadastro 10"))
    close, declined, address = (r.result for r in run_journey(turn_engine, CTX, list(steps)))
    assert declined.reply.template_ids == ("present_terms.needs_delivery_address_saved_declined",)
    assert declined.commands == ()
    assert [c.action for c in address.commands] == ["set_delivery_address"]
    assert world.state.address["cart-1"]["text"] == "Rua das Flores 120"
    assert address.reply.template_ids[-1] == "present_terms.confirm"  # o fechamento seguiu


def test_yes_to_the_payment_question_is_not_an_answer():
    """A forma de pagamento não é pergunta de sim ou não: o "sim" não escolhe pix."""
    world = FakeWorld()
    world.state.payment_methods = ("pix", "card")
    steps = (CLOSE, YES)
    turn_engine, world = engine(steps=steps, world=world)
    _close, yes = (r.result for r in run_journey(turn_engine, CTX, list(steps)))
    assert yes.commands == () and "cart-1" not in world.state.payment



# ── a revisão do #3455: o "sim" preso à pergunta, ao movimento e à opção oferecida ─────────────


def test_yes_is_bound_to_the_condition_question_not_to_any_later_question():
    """Oferecido o endereço do cadastro, a Nice pergunta outra coisa (o cliente disse algo que ela não entendeu):
    o "sim" seguinte responde à pergunta nova, nunca grava o endereço."""
    unclear = _step("unclear", {"act": "unknown"})
    steps = (CLOSE, unclear, YES)
    turn_engine, world = engine(steps=steps, world=_saved_world("Rua do Cadastro 10"))
    _close, asked, yes = (r.result for r in run_journey(turn_engine, CTX, list(steps)))
    assert asked.chosen_moves == ["ask_clarification"]
    assert yes.commands == () and "cart-1" not in world.state.address


def test_yes_takes_the_offered_address_even_if_the_book_changed():
    """O "sim" aceita a opção OFERECIDA. Se o cadastro mudou depois da oferta, a referência não casa e nada
    se grava com um endereço que o cliente não viu."""
    steps = (CLOSE, YES)
    world = _saved_world("Rua do Cadastro 10")
    turn_engine, world = engine(steps=steps, world=world)
    results = run_journey(turn_engine, CTX, list(steps[:1]))
    world.state.saved_addresses["cart-1"] = ["Rua Nova 99"]  # o cadastro mudou entre a oferta e o "sim"
    yes = run_journey(turn_engine, CTX, list(steps[1:]))[0].result
    assert results and [dict(c.parameters) for c in yes.commands] == [{"source": "saved:cart-1:0:ruadocadastro10"}]
    assert "cart-1" not in world.state.address  # a referência oferecida não casa com o cadastro de agora


def test_no_with_another_address_in_the_same_message_is_the_choice():
    """ "Não, entrega na Rua das Flores 120": o "não" é correção; ganha o endereço dito, e o fechamento segue."""
    both = JourneyStep(message=j4.message("no-other", "Rua das Flores 120"),
                       understanding={"acts": [{"act": "deny"}, {"act": "give_address"}]},
                       expect_moves=(), expect_text=(), advance_seconds=30)
    steps = (CLOSE, both)
    turn_engine, world = engine(steps=steps, world=_saved_world("Rua do Cadastro 10"))
    _close, chose = (r.result for r in run_journey(turn_engine, CTX, list(steps)))
    assert [c.action for c in chose.commands] == ["set_delivery_address"]
    assert world.state.address["cart-1"]["text"] == "Rua das Flores 120"
    assert "acknowledge.terms_declined" not in chose.reply.template_ids
    assert "present_terms.needs_delivery_address_saved_declined" not in chose.reply.template_ids


def test_the_condition_answer_is_only_for_the_move_that_declares_it():
    from conversational_commerce.engine.state import NeedSpec, TurnState

    state = TurnState.__new__(TurnState)
    state.needs = (NeedSpec("n1", "affirm", answers_question="q-1"),)
    state.condition_question = {"question_id": "q-1", "code": "delivery_address_saved", "ref": "saved:x"}
    need = state.needs[0]
    assert state.answers_condition(need, ("delivery_address_saved",))
    assert not state.answers_condition(need, ("payment_method",))  # outro movimento não responde a esta pergunta
    other = NeedSpec("n1", "affirm", answers_question="q-2")
    assert not state.answers_condition(other, ("delivery_address_saved",))  # outra pergunta
