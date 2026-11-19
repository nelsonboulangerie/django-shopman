"""As falhas injetáveis de cada falso fazem o que o nome diz."""

from __future__ import annotations

import dataclasses

import pytest

from conversational_commerce.contracts import ActionCommand, Unknown, command_content_hash
from conversational_commerce.ports import (
    Budget,
    InterpretRequest,
    ModelRequest,
    PortError,
    PreparedMessage,
    StaffQuestion,
    Transition,
    WorkItem,
)
from conversational_commerce.testing.conformance.harness import AllowGuard, RefuseGuard
from conversational_commerce.testing.fakes import FakeChannel, FakeWorld, Fault


def _command(world: FakeWorld, ctx, terms, *, key="k-1", parameters=None) -> ActionCommand:
    parameters = parameters or {}
    return ActionCommand(
        id=world.clock.new_id("cmdrec"), tenant=ctx.tenant, environment=ctx.environment, trace_id="t",
        occurred_at=world.clock.now(), producer={"name": "test", "version": "1"}, episode_id="ep-1",
        command_id=world.clock.new_id("command"), decision_id="d-1", grant_id="g-1", action="commit_order",
        targets=("cart-1",), parameters=parameters, terms_hash=terms.hash, expected_versions={},
        expected_ownership_epoch=0, idempotency={"scope": "commit_order", "key": key},
        content_hash=command_content_hash(action="commit_order", targets=("cart-1",), parameters=parameters,
                                          terms_hash=terms.hash),
        deadline=world.clock.at(600),
    )


def test_fault_plan_fires_once_per_arm():
    world = FakeWorld()
    world.faults.arm("read_item", Fault.SOURCE_FAILED)
    assert world.faults.pending() == {"read_item": [Fault.SOURCE_FAILED]}
    assert world.faults.take("read_item") is Fault.SOURCE_FAILED
    assert world.faults.take("read_item") is None


def test_channel_duplicates_and_reorders(world):
    world.channel.deliver({"id": "m1"}, {"id": "m2"})
    world.faults.arm("drain", Fault.DUPLICATE_DELIVERY)
    assert [raw["id"] for raw in world.channel.drain()] == ["m1", "m2", "m1"]
    world.channel.deliver({"id": "m1"}, {"id": "m2"})
    world.faults.arm("drain", Fault.OUT_OF_ORDER)
    assert [raw["id"] for raw in world.channel.drain()] == ["m2", "m1"]


def test_duplicate_delivery_is_recorded_once(world, ctx):
    world.channel.deliver({"id": "m1", "from": "a"})
    world.faults.arm("drain", Fault.DUPLICATE_DELIVERY)
    created = [world.store.record_event_once(ctx, world.channel.normalize(ctx, raw, world.clock.now()))[1]
               for raw in world.channel.drain()]
    assert created == [True, False]


def test_message_without_identity_is_never_deduplicated(world, ctx):
    events = [world.channel.normalize(ctx, {"content_ref": "text:same"}, world.clock.now()) for _ in range(2)]
    assert [world.store.record_event_once(ctx, event)[1] for event in events] == [True, True]


def test_send_unknown_and_no_read_channel(world, ctx):
    channel = FakeChannel(world.clock, world.faults, read_receipts=False)
    world.faults.arm("send", Fault.SEND_UNKNOWN)
    event = channel.normalize(ctx, {"id": "m1"}, world.clock.now())
    prepared = PreparedMessage(decision_id="d", content_hash="sha256:" + "0" * 64, recipient="r",
                               binding=event.channel_binding, body_ref="b")
    exposure = channel.send(ctx, prepared, "key")
    assert exposure.state == "unknown"
    assert channel.send(ctx, prepared, "key").id == exposure.id  # não reenvia às cegas
    channel.mark("key", "delivered")
    with pytest.raises(ValueError):
        channel.mark("key", "read")
    assert "read_receipts" in channel.capabilities().unsupported


@pytest.mark.parametrize(
    ("fault", "code"),
    [(Fault.PROVIDER_DOWN, "provider_unavailable"), (Fault.BUDGET_EXHAUSTED, "budget_exhausted"),
     (Fault.OUT_OF_SCHEMA, "invalid_content")],
)
def test_model_failures_are_typed(world, ctx, fault, code):
    world.faults.arm("interpret", fault)
    request = InterpretRequest(request=ModelRequest(purpose="p", budget=Budget(max_calls=3, max_spend={
        "amount_minor": 0, "currency": "XTS"}), data_class="redacted"), event_id="e", content_ref="text:hours",
        allowed_acts=("ask_hours",))
    with pytest.raises(PortError) as caught:
        world.model.interpret(ctx, request)
    assert caught.value.code == code


def test_model_act_outside_list_and_unpriced_consumption(world, ctx):
    world.faults.arm("interpret", Fault.ACT_OUTSIDE_LIST)
    request = InterpretRequest(request=ModelRequest(purpose="p", budget=Budget(max_calls=1, max_spend={
        "amount_minor": 0, "currency": "XTS"}), data_class="redacted"), event_id="e", content_ref="text:hours",
        allowed_acts=("ask_hours",))
    understanding, consumption = world.model.interpret(ctx, request)
    assert "transfer_all_funds" in [act.act for act in understanding.acts]
    assert consumption.cost.status == "unavailable"  # sem preço: desconhecido, nunca zero (K34)
    with pytest.raises(PortError) as caught:
        world.model.interpret(ctx, request)
    assert caught.value.code == "budget_exhausted"


@pytest.mark.parametrize(("fault", "reason"), [(Fault.SOURCE_FAILED, "source_failed"), (Fault.STALE_FACT, "stale")])
def test_commerce_read_source_failure_and_stale(world, ctx, fault, reason):
    world.faults.arm("read_item", fault)
    assert world.commerce_read.read_item(ctx, "ITEM-A") == Unknown(reason=reason)


def test_promise_is_four_readings_never_reserved(world, ctx):
    from conversational_commerce.contracts import Quantity

    reading = world.commerce_read.promise(ctx, "ITEM-B", Quantity(value="3", unit="unit"), world.clock.now())
    assert reading.factual.value == "0"  # nada em mãos
    assert reading.promisable.value is True  # mas pode prometer, pelo esperado (K27)


def test_price_change_after_quote_invalidates_the_terms(world, ctx):
    world.faults.arm("quote", Fault.PRICE_CHANGES_AFTER_QUOTE)
    terms = world.commerce_read.quote(ctx, "cart-1")
    assert "cart-1" not in world.state.current_terms
    fresh = world.commerce_read.quote(ctx, "cart-1")
    assert fresh.hash != terms.hash and fresh.total.amount_minor > terms.total.amount_minor


def test_object_authorization_on_reads(world, ctx):
    with pytest.raises(PortError) as caught:
        world.commerce_read.read_customer(ctx, "customer-2")
    assert caught.value.code == "object_forbidden"
    other = dataclasses.replace(ctx, subject="customer-2")
    with pytest.raises(PortError):
        world.commerce_read.quote(other, "cart-1")


def test_crash_before_effect_leaves_no_effect_and_reconciles_as_not_applied(world, ctx):
    terms = world.commerce_read.quote(ctx, "cart-1")
    command = _command(world, ctx, terms)
    world.faults.arm("execute", Fault.CRASH_BEFORE_EFFECT)
    with pytest.raises(PortError) as caught:
        world.commerce_execute.execute(ctx, command, AllowGuard())
    assert caught.value.code == "effect_unknown" and caught.value.may_have_happened
    assert world.commerce_execute.effects == 0
    receipt = world.commerce_execute.reconcile(ctx, command)
    assert (receipt.status, receipt.effect) == ("failure", "not_applied")


def test_crash_after_effect_reconciles_to_the_original_effect(world, ctx):
    terms = world.commerce_read.quote(ctx, "cart-1")
    command = _command(world, ctx, terms)
    world.faults.arm("execute", Fault.CRASH_AFTER_EFFECT)
    with pytest.raises(PortError):
        world.commerce_execute.execute(ctx, command, AllowGuard())
    assert world.commerce_execute.effects == 1
    receipt = world.commerce_execute.reconcile(ctx, command)
    assert (receipt.status, receipt.effect) == ("success", "applied")
    # Repetir com a MESMA chave não cria segundo efeito.
    assert world.commerce_execute.execute(ctx, command, AllowGuard()).id == receipt.id
    assert world.commerce_execute.effects == 1


def test_pending_effect_has_reconciliation(world, ctx):
    terms = world.commerce_read.quote(ctx, "cart-1")
    world.faults.arm("execute", Fault.EFFECT_PENDING)
    receipt = world.commerce_execute.execute(ctx, _command(world, ctx, terms), AllowGuard())
    assert (receipt.status, receipt.effect) == ("pending", "unknown")
    assert receipt.reconciliation is not None


def test_guard_sees_the_current_terms_and_refusal_leaves_no_effect(world, ctx):
    world.faults.arm("quote", Fault.PRICE_CHANGES_AFTER_QUOTE)
    terms = world.commerce_read.quote(ctx, "cart-1")
    guard = AllowGuard()
    world.commerce_execute.execute(ctx, _command(world, ctx, terms), guard)
    assert guard.seen[0].terms_hash is None  # os termos confirmados já não são os vigentes
    refused = world.commerce_execute.execute(ctx, _command(world, ctx, terms, key="k-2"), RefuseGuard("terms_changed"))
    assert refused.error.code == "terms_changed"
    assert world.commerce_execute.effects == 1


def test_staff_queue_rejects_and_late_answer(world, ctx):
    world.faults.arm("ask", Fault.QUEUE_REJECTS)
    rejected = world.staff.ask(ctx, StaffQuestion(episode_id="ep", question="q", respond_by=world.clock.at(600)))
    assert rejected.state == "rejected"
    with pytest.raises(PortError):
        world.staff.record_acceptance(ctx, rejected.ticket_id)
    ticket = world.staff.ask(ctx, StaffQuestion(episode_id="ep", question="q", respond_by=world.clock.at(600)))
    world.staff.record_acceptance(ctx, ticket.ticket_id)
    world.faults.arm("answer", Fault.LATE_ANSWER)
    answered = world.staff.answer(ticket.ticket_id, "yes")
    assert answered.answer.observed_at > world.staff.questions[ticket.ticket_id].respond_by
    assert answered.answer.source == "staff:staff-1"


def test_store_version_conflict_worker_death_and_double_claim(world, ctx):
    from conversational_commerce.contracts import Episode

    episode = Episode(id="r1", tenant=ctx.tenant, environment="test", trace_id="t", occurred_at=world.clock.now(),
                      producer={"name": "t", "version": "1"}, episode_id="ep-1", state="active", version=1,
                      ownership={"owner": "automation", "epoch": 0}, opened_at=world.clock.now())
    work = WorkItem(work_id="w1", kind="reconcile", payload={}, due_at=world.clock.now())
    world.store.commit_transition(ctx, Transition(episode=episode, expected_version=0), (), (work,))
    world.faults.arm("commit_transition", Fault.VERSION_CONFLICT)
    with pytest.raises(PortError) as caught:
        world.store.commit_transition(ctx, Transition(episode=dataclasses.replace(episode, version=2),
                                                      expected_version=1), (), ())
    assert caught.value.code == "revision_conflict"
    world.faults.arm("claim_work", Fault.WORKER_DIES)
    first = world.store.claim_work(ctx, "reconcile", 60)
    second = world.store.claim_work(ctx, "reconcile", 60)
    assert (first.attempt, second.attempt) == (1, 2)  # a reivindicação venceu: o trabalho voltou
    assert world.store.claim_work(ctx, "reconcile", 60) is None
    world.faults.arm("claim_work", Fault.DOUBLE_CLAIM)
    assert world.store.claim_work(ctx, "reconcile", 60).attempt == 3


def test_outcomes_immature_unknown_and_correction(world, ctx):
    from conversational_commerce.contracts import MetricRef, Window

    metric = MetricRef(id="repurchase", definition_version="1")
    past = Window(start="2025-12-01T00:00:00.000000Z", end="2025-12-31T00:00:00.000000Z")
    assert world.outcomes.harvest(ctx, metric, "customer-1", past).observation == "unknown"
    world.outcomes.seed("repurchase", "customer-1", 1)
    first = world.outcomes.harvest(ctx, metric, "customer-1", past)
    assert (first.observation, first.value) == ("observed", 1)
    world.faults.arm("harvest", Fault.CORRECTED_LATER)
    world.outcomes.seed("repurchase", "customer-1", 0)
    corrected = world.outcomes.harvest(ctx, metric, "customer-1", past)
    assert corrected.supersedes == first.id
    world.faults.arm("harvest", Fault.IMMATURE)
    assert world.outcomes.harvest(ctx, metric, "customer-1", past).observation == "censored"


def test_clock_is_deterministic_and_due_work_is_claimable(world):
    assert world.clock.new_id("x") == "x-0001"
    work = WorkItem(work_id="w", kind="deadline", payload={}, due_at=world.clock.at(60))
    world.clock.schedule(world.clock.at(60), work)
    assert world.clock.due() == []
    world.clock.advance(60)
    assert world.clock.due() == [work]
    with pytest.raises(ValueError):
        world.clock.advance(-1)
