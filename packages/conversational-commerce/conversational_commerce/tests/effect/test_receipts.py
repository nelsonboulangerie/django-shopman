"""O livro dos recibos e a reconciliação: K08, K09, K12, K14, K16."""

from __future__ import annotations

import dataclasses

import pytest

from conversational_commerce.contracts import Episode, Wait
from conversational_commerce.ledger import LedgerError, ReceiptLedger, Settler, next_step, work_execution
from conversational_commerce.ports import Capabilities, PortError, Transition, WorkItem
from conversational_commerce.testing.conformance import conformance
from conversational_commerce.testing.fakes import FakeCommerceExecute, FakeWorld, Fault
from conversational_commerce.workflow import EpisodeEvent, open_episode, transition

from .helpers import CTX, Bench, record


def _setup(world=None):
    bench = Bench.make(world)
    grant = bench.grant()
    command = bench.command(grant)
    return bench, grant, command


def test_success_answers_and_a_late_receipt_does_not_reopen():
    bench, grant, command = _setup()
    settler = bench.settler()
    settled = settler.settle(CTX, command, bench.guard(grant, command))
    assert settled.step == "execute" and settled.receipt.status == "success"
    assert next_step(settler.ledger, command, now=bench.world.clock.now(), retention=3600) == "done"
    late = bench.world.commerce_execute._pending(CTX, command, "pending")
    settler.ledger.append(late)
    assert settler.ledger.latest(command.command_id).status == "success"  # evidência, não autorização


def test_failure_is_final_and_a_new_intent_needs_a_new_decision():
    world = FakeWorld()
    world.faults.arm("quote", Fault.PRICE_CHANGES_AFTER_QUOTE)
    bench, grant, command = _setup(world)
    settler = bench.settler()
    assert settler.settle(CTX, command, bench.guard(grant, command)).receipt.status == "failure"
    again = settler.settle(CTX, command, bench.guard(grant, command))
    assert again.step == "failed" and world.commerce_execute.calls.count("execute") == 1


@conformance("K08", invariants=("N08", "N09"), scope="adapter")
def test_k08_same_key_and_content_after_a_lost_response():
    world = FakeWorld()
    bench, grant, command = _setup(world)
    world.faults.arm("execute", Fault.CRASH_AFTER_EFFECT)
    settler = bench.settler()
    lost = settler.settle(CTX, command, bench.guard(grant, command))
    assert (lost.receipt.status, lost.receipt.effect) == ("unknown", "unknown")  # nunca falha
    # O executor devolve o recibo existente para a mesma chave e o mesmo conteúdo.
    assert world.commerce_execute.execute(CTX, command, bench.guard(grant, command)).status == "success"
    settled = settler.settle(CTX, command, bench.guard(grant, command))
    assert settled.step == "reconcile" and settled.receipt.status == "success"
    assert world.commerce_execute.effects == 1 and len(world.state.orders) == 1
    assert settled.receipt.supersedes is not None


@conformance("K09", invariants=("N08",), scope="adapter")
def test_k09_same_key_with_different_content():
    bench, grant, command = _setup()
    settler = bench.settler()
    first = settler.settle(CTX, command, bench.guard(grant, command)).receipt
    other = bench.command(grant, parameters={"note": "changed"})
    other = dataclasses.replace(other, idempotency=command.idempotency)
    with pytest.raises(LedgerError, match="idempotency_conflict"):
        settler.ledger.register(other)
    conflict = Settler(ReceiptLedger(), bench.world.commerce_execute, bench.world.clock, bench.profile).settle(
        CTX, other, bench.guard(grant, other))
    assert conflict.conflict == "idempotency_conflict"
    located = bench.world.commerce_execute.locate(CTX, command.idempotency.scope, command.idempotency.key)
    assert located.id == first.id  # o recibo não foi sobrescrito
    assert bench.world.commerce_execute.effects == 1


@conformance("K12", invariants=("N10",), scope="real_mechanism")
def test_k12_handoff_after_the_external_submission():
    world = FakeWorld()
    bench, grant, command = _setup(world)
    world.faults.arm("execute", Fault.EFFECT_PENDING)
    settler = bench.settler()
    pending = settler.settle(CTX, command, bench.guard(grant, command)).receipt
    assert pending.status == "pending" and pending.reconciliation.owner == "core"
    # A pessoa assume com o efeito já submetido: a época sobe.
    episode = open_episode(record_id="r1", episode_id=command.episode_id, tenant=CTX.tenant,
                           environment=CTX.environment, trace_id="t", at=world.clock.now(),
                           producer=record(world, "x")["producer"], subject="s")
    episode = transition(episode, EpisodeEvent(kind="handoff_requested", at=world.clock.now(), cause_id="c",
                                               wait=Wait(condition="a person takes over", owner="queue",
                                                         deadline=world.clock.at(600))),
                         expected_version=1, record_id="r2")
    world.commerce_execute.epochs[command.episode_id] = episode.ownership.epoch
    world.commerce_execute.complete_pending(command.command_id)  # o provedor conclui
    settled = settler.settle(CTX, command, None)
    assert settled.step == "reconcile" and settled.receipt.status == "success"
    # Reconciliado com a mesma chave, sem guarda nova e sem comando novo: nada se desfaz.
    assert world.commerce_execute.effects == 1 and list(settler.ledger.commands) == [command.command_id]


@conformance("K14", invariants=("N09",), scope="real_mechanism")
def test_k14_worker_dies_in_the_middle_of_the_execution():
    world = FakeWorld()
    bench, grant, command = _setup(world)
    episode = Episode(**record(world, "eprec"), state="active", version=1,
                      ownership={"owner": "automation", "epoch": 0}, opened_at=world.clock.now())
    work = WorkItem(work_id=f"execute:{command.command_id}", kind="execute",
                    payload={"command_id": command.command_id}, due_at=world.clock.now())
    world.store.commit_transition(CTX, Transition(episode=episode, expected_version=0), (grant, command), (work,))
    settler = bench.settler()
    settler.ledger.register(command)
    # O primeiro trabalhador reivindica, aplica o efeito e morre antes de gravar o recibo.
    world.faults.arm("claim_work", Fault.WORKER_DIES)
    claim = world.store.claim_work(CTX, "execute", 60)
    world.faults.arm("execute", Fault.CRASH_AFTER_EFFECT)
    with pytest.raises(PortError):
        world.commerce_execute.execute(CTX, command, bench.guard(grant, command))
    assert claim.attempt == 1 and settler.ledger.latest(command.command_id) is None
    # O próximo reconcilia antes de repetir, com a mesma chave.
    settled = work_execution(CTX, store=world.store, settler=settler,
                             guard_for=lambda c: bench.guard(grant, c))
    assert settled.step == "reconcile" and settled.receipt.status == "success"
    assert world.commerce_execute.effects == 1 and len(world.state.orders) == 1
    assert world.store.claim_work(CTX, "execute", 60) is None  # concluído, sai da caixa de saída


class ShortRetention(FakeCommerceExecute):
    def capabilities(self) -> Capabilities:
        base = super().capabilities()
        return Capabilities(port=base.port, operations=base.operations,
                            guarantees={**base.guarantees, "idempotency_retention_seconds": 60})


@conformance("K16", invariants=("N09",), scope="adapter")
def test_k16_expired_key_with_an_unknown_previous_effect():
    world = FakeWorld()
    executor = ShortRetention(world.clock, world.faults, world.state)
    bench, grant, command = _setup(world)
    settler = bench.settler(executor)
    world.faults.arm("execute", Fault.CRASH_BEFORE_EFFECT)
    unknown = settler.settle(CTX, command, bench.guard(grant, command)).receipt
    assert unknown.status == "unknown"
    world.clock.advance(120)  # a chave venceu; o prazo da reconciliação, não
    blocked = settler.settle(CTX, command, bench.guard(grant, command))
    assert blocked.to_person and executor.calls.count("execute") == 1  # nunca executa de novo
    assert ("locate" in executor.calls) and executor.effects == 0


def test_overdue_reconciliation_goes_to_a_person():
    world = FakeWorld()
    bench, grant, command = _setup(world)
    world.faults.arm("execute", Fault.EFFECT_PENDING)
    settler = bench.settler()
    settler.settle(CTX, command, bench.guard(grant, command))
    world.clock.advance(900)
    assert settler.settle(CTX, command, None).to_person
    # A máquina do F4 leva o episódio a uma pessoa, e a época sobe.
    episode = open_episode(record_id="r1", episode_id="e", tenant=CTX.tenant, environment=CTX.environment,
                           trace_id="t", at=world.clock.now(), producer=record(world, "x")["producer"], subject="s")
    for kind in ("command_handed_off", "reconciliation_overdue"):
        episode = transition(episode, EpisodeEvent(kind=kind, at=world.clock.now(), cause_id="c",
                                                   wait=Wait(condition="x", owner="core",
                                                             deadline=world.clock.at(600))),
                             expected_version=episode.version, record_id=f"r-{kind}")
    assert episode.state == "awaiting_handoff" and episode.ownership.epoch == 1
