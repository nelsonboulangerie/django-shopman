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
