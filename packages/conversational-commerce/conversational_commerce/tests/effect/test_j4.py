"""J4 de ponta a ponta sobre os falsos, e o contrato de efeito dentro do turno."""

from __future__ import annotations

import dataclasses

from conversational_commerce.ports import TrustedContext
from conversational_commerce.testing.conformance import conformance
from conversational_commerce.testing.fakes import Fault
from conversational_commerce.testing.fakes.synthetic_domain import START
from conversational_commerce.testing.journeys import j4, run_journey

from .helpers import CTX, engine


def _yes(mid: str, **extra):
    return dataclasses.replace(j4.CONFIRM, message=j4.message(mid, "yes", **extra))


def test_j4_order_with_effect():
    turn_engine, world = engine()
    results = run_journey(turn_engine, CTX, j4.STEPS)
    assert [r.problems for r in results] == [(), (), ()]
    changed, quoted, placed = (r.result for r in results)
    assert changed.grants[0].basis == "profile_line" and world.state.carts["cart-1"]["ITEM-A"] == "3"
    assert quoted.commands == () and quoted.episode.state == "waiting_authorization"
    grant, command, receipt = placed.grants[0], placed.commands[0], placed.receipts[0]
    assert grant.basis == "customer_confirmation" and grant.terms_hash == command.terms_hash
    assert (receipt.status, receipt.effect) == ("success", "applied")
    assert placed.reply.plan.parts[0].claims[0].backing == "receipt"  # o efeito afirmado tem recibo
    assert len(world.state.orders) == 1 and world.commerce_execute.effects == 2
    # N13: concessão e comando gravados, e a execução saiu da caixa de saída.
    kinds = {type(record).__name__ for _, record in world.store.records}
    assert {"AuthorizationGrant", "ActionCommand"} <= kinds
    assert not [w for w in world.store.outbox if w.startswith("execute:")]
    assert [r.status for _, r in world.store.receipts] == ["success", "success"]


def test_without_the_subject_cart_a_change_is_a_limitation():
    turn_engine, world = engine()
    turn_engine.subject_of = lambda ctx, event: j4.subject(TrustedContext(tenant=ctx.tenant,
                                                                          environment=ctx.environment), event)
    [result] = run_journey(turn_engine, CTX, [dataclasses.replace(j4.CHANGE, expect_moves=("inform_limitation",),
                                                                  expect_text=())])
    assert result.problems == () and world.commerce_execute.calls == []


def test_without_the_grant_line_nothing_is_executed():
    lines = tuple(line for line in engine()[0].profile.lines if line.id != "grant.validity_seconds")
    turn_engine, world = engine(profile_overrides={**_with_model(), "lines": lines})
    result = turn_engine.turn(CTX, j4.CHANGE.message)
    assert "grant_refused:profile_line_absent" in result.fallbacks
    assert result.chosen_moves == ["inform_limitation"] and world.commerce_execute.calls == []
    assert result.decisions[1].parent_decision_id == result.decisions[0].decision_id


def _with_model():
    from conversational_commerce.tests.engine.helpers import WITH_MODEL

    return dict(WITH_MODEL)


def test_yes_without_terms_is_only_an_acknowledgement():
    turn_engine, world = engine()
    result = turn_engine.turn(CTX, j4.CONFIRM.message)
    assert result.chosen_moves == ["acknowledge"] and world.state.orders == {}


def test_k03_yes_sent_before_the_terms_arrives_after_them():
    turn_engine, world = engine()
    run_journey(turn_engine, CTX, j4.STEPS[:2])
    world.clock.advance(30)
    early = turn_engine.turn(CTX, j4.message("j4-early", "yes", sent_at=START))
    assert world.state.orders == {}
    blocked = next(c for c in early.decision.candidates if c.move == "commit_order")
    assert "confirmation_before_terms" in blocked.blocked_by
    assert early.chosen_moves == ["present_terms"] and early.episode.state == "waiting_authorization"
    # Na ordem certa, o mesmo estado final que sem a confirmação fora de ordem.
    [placed] = run_journey(turn_engine, CTX, [_yes("j4-m4")])
    assert placed.problems == () and len(world.state.orders) == 1


def test_k07_price_changes_after_the_quote_asks_again():
    turn_engine, world = engine()
    run_journey(turn_engine, CTX, j4.STEPS[:1])
    world.faults.arm("quote", Fault.PRICE_CHANGES_AFTER_QUOTE)
    run_journey(turn_engine, CTX, [j4.QUOTE])
    [refused] = run_journey(turn_engine, CTX, [dataclasses.replace(
        j4.CONFIRM, expect_moves=("present_terms",), expect_text=("The terms changed", "XTS 15.00"),
        expect_state="waiting_authorization")])
    assert refused.problems == ()
    result = refused.result
    assert result.receipts[0].error.code == "terms_changed" and world.state.orders == {}
    first, second = result.decisions
    assert [first.candidates[i].move for i in first.chosen] == ["commit_order"]
    assert second.parent_decision_id == first.decision_id  # decisão nova, ligada; a anterior não muda
    [placed] = run_journey(turn_engine, CTX, [_yes("j4-m4")])
    assert placed.problems == () and len(world.state.orders) == 1
    assert placed.result.commands[0].terms_hash != result.commands[0].terms_hash


@conformance("K10", invariants=("N09", "N13"), scope="adapter")
def test_k10_crash_after_the_effect_is_reconciled_to_the_original_order():
    turn_engine, world = engine()
    run_journey(turn_engine, CTX, j4.STEPS[:2])
    world.faults.arm("execute", Fault.CRASH_AFTER_EFFECT)
    [lost] = run_journey(turn_engine, CTX, [dataclasses.replace(
        j4.CONFIRM, expect_moves=("commit_order",), expect_text=("still in progress",),
        expect_state="waiting_effect")])
    assert lost.problems == () and lost.result.receipts[0].status == "unknown"
    assert "placed" not in lost.result.text  # efeito desconhecido não vira confirmação
    command = lost.result.commands[0]
    settled = turn_engine.reconcile(CTX, command.command_id)
    assert settled.receipt.status == "success"
    [order] = world.state.orders
    assert settled.receipt.domain_refs["effect"] == order and world.commerce_execute.effects == 2
    assert world.store.load_episode(CTX, command.episode_id).state == "active"


def test_shadow_decides_but_never_executes():
    turn_engine, world = engine()
    shadow = TrustedContext(tenant=CTX.tenant, environment="shadow", subject=CTX.subject)
    result = turn_engine.turn(shadow, j4.CHANGE.message)
    assert result.outcome == "shadow" and result.chosen_moves == ["change_cart"]
    assert "shadow:effect_not_executed:change_cart" in result.fallbacks
    assert world.commerce_execute.calls == [] and world.channel.outbox == {}


def test_moves_without_an_act_only_live_as_preconditions():
    from conversational_commerce.engine.moves import registry
    from conversational_commerce.profile.test_profile import build_test_profile

    moves = registry()
    discount = moves["grant_discount"]
    profile = build_test_profile()
    assert discount.cap_minor(profile) == 500
    assert discount.within_cap(profile, 500) and not discount.within_cap(profile, 501)
    assert not discount.within_cap(profile, 0)
    # Linha não aprovada: nenhum desconto.
    lines = tuple(dataclasses.replace(line, state="proposed") if line.id == "commerce.discount_cap_minor" else line
                  for line in profile.lines)
    without = build_test_profile(lines=lines)
    assert discount.cap_minor(without) is None and not discount.within_cap(without, 100)
    # Cancelar é julgado, mas sem a janela e sem a confirmação presa ao pedido fica inelegível.
    turn_engine, world = engine(steps=(dataclasses.replace(j4.CHANGE, understanding={"acts": [
        {"act": "cancel_order", "fields": {"order": "order-9"}}]}),))
    result = turn_engine.turn(CTX, j4.CHANGE.message)
    assert result.chosen_moves == ["inform_limitation"] and world.commerce_execute.calls == []
