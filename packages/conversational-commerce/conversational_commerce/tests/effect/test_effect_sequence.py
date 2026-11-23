"""A sequência de efeitos A2 num turno (spec 08 §5, [DECIDIDO]; dono, 23/11/2026: a saída (d) da #3374).

"Quero 2 croissants, amanhã vou buscar" é o recebimento e a sacola: dois efeitos A2 reversíveis.
Saem em sequência declarada (o recebimento antes), cada um com a própria concessão, o próprio
comando, a intenção gravada antes (N13) e o próprio recibo. A sequência para no primeiro recibo que
não é sucesso: há no máximo uma espera de efeito e uma reconciliação aberta por vez. O
``commit_order`` (A3) nunca entra nela.
"""

from __future__ import annotations

from conversational_commerce.testing.fakes import Fault
from conversational_commerce.testing.journeys import j4
from conversational_commerce.testing.journeys.runner import JourneyStep

from .helpers import CTX, engine

TOMORROW = "2026-01-06"  # o relógio sintético começa em 2026-01-05
A3 = {"act": "change_quantity", "fields": {"item": "ITEM-A", "quantity": "3"}}
PICKUP = {"act": "choose_fulfillment", "fields": {"date": TOMORROW, "mode": "pickup"}}


def _step(*acts, mid="seq-1"):
    return JourneyStep(message=j4.message(mid, "both"), understanding={"acts": list(acts)},
                       expect_moves=(), expect_text=())


def test_the_cart_and_the_fulfillment_run_in_the_declared_order_each_with_its_receipt():
    step = _step(A3, PICKUP)  # a cliente diz a sacola primeiro; a ordem é a declarada
    turn_engine, world = engine(steps=(step,))
    result = turn_engine.turn(CTX, step.message)
    assert [c.action for c in result.commands] == ["set_fulfillment", "change_cart"]
    assert len({g.id for g in result.grants}) == 2 and len(result.receipts) == 2
    assert {c.idempotency.key for c in result.commands}.__len__() == 2  # uma chave por efeito
    assert world.state.carts["cart-1"]["ITEM-A"] == "3"
    assert world.state.fulfillment["cart-1"] == {"date": TOMORROW, "mode": "pickup"}
    backed = [(part.move, {c.ref for c in part.claims if c.backing == "receipt"}) for part in result.reply.plan.parts]
    assert len({ref for _, refs in backed for ref in refs}) == 2  # cada parte cita o próprio recibo (K24)
    assert result.episode.state == "active"


def test_the_sequence_stops_at_the_first_failure():
    gone = {"act": "choose_fulfillment", "fields": {"date": "2026-01-04"}}  # o dia já passou
    step = _step(A3, gone)
    turn_engine, world = engine(steps=(step,))
    result = turn_engine.turn(CTX, step.message)
    assert [c.action for c in result.commands] == ["set_fulfillment"]
    assert result.receipts[0].status == "failure"
    assert world.state.carts["cart-1"] == {"ITEM-A": "2"}  # a sacola não muda depois da recusa
    assert world.commerce_execute.effects == 0
    # A sacola não foi impossível: só não foi tentada. O texto diz isso, nunca "I can't do that here".
    assert "That part waits until the earlier step is settled" in result.text
    assert "inform_limitation.not_attempted" in result.reply.template_ids


def test_the_sequence_stops_at_a_pending_receipt_with_one_reconciliation():
    step = _step(A3, PICKUP)
    turn_engine, world = engine(steps=(step,))
    world.faults.arm("execute", Fault.EFFECT_PENDING)
    result = turn_engine.turn(CTX, step.message)
    assert [c.action for c in result.commands] == ["set_fulfillment"]
    assert result.receipts[0].status == "pending"
    assert world.state.carts["cart-1"] == {"ITEM-A": "2"}
    assert result.episode.state == "waiting_effect"  # uma espera de efeito, a do primeiro
    assert "That part waits until the earlier step is settled" in result.text


def test_the_same_turn_twice_applies_each_effect_once():
    step = _step(A3, PICKUP)
    turn_engine, world = engine(steps=(step,))
    turn_engine.turn(CTX, step.message)
    again = turn_engine.turn(CTX, step.message)
    assert again.outcome == "duplicate" and world.commerce_execute.effects == 2


def _yes_with_a_change(*acts):
    from conversational_commerce.testing.journeys import run_journey

    step = JourneyStep(message=j4.message("seq-yes", "yes and four"), understanding={"acts": list(acts)},
                       expect_moves=(), expect_text=(), advance_seconds=30)
    turn_engine, world = engine(steps=(j4.CHANGE, j4.QUOTE, step))
    *_, last = run_journey(turn_engine, CTX, [j4.CHANGE, j4.QUOTE, step])
    return last.result, world


FOUR = {"act": "change_quantity", "fields": {"item": "ITEM-A", "quantity": "4"}}


def test_yes_with_a_change_of_the_same_cart_never_places_the_order():
    """Revisão do #3384: "sim, e põe quatro" não grava o pedido de 3 (v2 4.7, propriedade 2)."""
    result, world = _yes_with_a_change({"act": "affirm"}, FOUR)
    assert "commit_order" not in [c.action for c in result.commands] and world.state.orders == {}
    assert world.state.carts["cart-1"] == {"ITEM-A": "4"}  # a mudança, sim, vale


def test_the_order_of_the_words_never_changes_the_outcome():
    """ "Põe quatro, sim" dá o mesmo: o pedido não é gravado pelos termos de antes."""
    result, world = _yes_with_a_change(FOUR, {"act": "affirm"})
    assert "commit_order" not in [c.action for c in result.commands] and world.state.orders == {}
    assert world.state.carts["cart-1"] == {"ITEM-A": "4"}



def test_the_second_grant_refused_never_walks_the_first_receipt_twice(monkeypatch):
    """Revisão do #3384: a concessão do SEGUNDO efeito recusada não derruba o turno depois do efeito feito."""
    from conversational_commerce.authority import GrantRefused
    from conversational_commerce.engine import turn as turn_module

    original = turn_module.issue_line_grant

    def refuse_the_cart(**kwargs):
        if kwargs["action"] == "change_cart":
            raise GrantRefused("profile_line_absent", "sem linha para a sacola (K39)")
        return original(**kwargs)

    monkeypatch.setattr(turn_module, "issue_line_grant", refuse_the_cart)
    step = _step(A3, PICKUP)
    turn_engine, world = engine(steps=(step,))
    result = turn_engine.turn(CTX, step.message)  # antes: InvalidTransition depois do recebimento feito
    assert [c.action for c in result.commands] == ["set_fulfillment"]
    assert world.state.fulfillment["cart-1"] == {"date": TOMORROW, "mode": "pickup"}
    assert result.episode.state == "active"
