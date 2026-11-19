"""K01, K02, K13 e K29: os testes de conformidade do episódio."""

from __future__ import annotations

from conversational_commerce.contracts import Producer
from conversational_commerce.ports import Transition, TrustedContext, WorkItem
from conversational_commerce.testing.conformance import conformance
from conversational_commerce.testing.fakes import FakeWorld, Fault
from conversational_commerce.workflow import (
    EpisodeEvent,
    advance,
    answer_refers_to,
    ask,
    handle_inbound,
    on_conversation_returned,
    open_episode,
    transition,
)

from .helpers import WAIT

CTX = TrustedContext(tenant="tenant-a", environment="test")


def _world_with_episode() -> tuple[FakeWorld, object]:
    world = FakeWorld()
    episode = open_episode(record_id=world.clock.new_id("eprec"), episode_id="ep-1", tenant="tenant-a",
                           environment="test", trace_id="trace-1", at=world.clock.now(),
                           producer=Producer(name="core", version="1"), subject="subject:customer-1")
    world.store.commit_transition(CTX, Transition(episode=episode, expected_version=0), (episode,), ())
    return world, episode


@conformance("K01", invariants=("N12",), scope="adapter")
def test_k01_same_input_twice_is_one_input_and_no_duplicated_work():
    world = FakeWorld()
    calls = []
    world.channel.deliver({"id": "provider-msg-1", "from": "addr-1", "content_ref": "text:hours?"})
    world.faults.arm("drain", Fault.DUPLICATE_DELIVERY)
    results = [handle_inbound(CTX, raw, calls.append, channel=world.channel, store=world.store, clock=world.clock)
               for raw in world.channel.drain()]
    assert [received.created for received, _ in results] == [True, False]
    assert len(calls) == 1, "a duplicata chegou ao trabalho"
    assert results[1][0].event.id == results[0][0].event.id  # devolve a entrada que já existia


@conformance("K02", invariants=("N12",), scope="adapter")
def test_k02_same_text_different_identities_are_both_kept():
    world = FakeWorld()
    calls = []
    for provider_id in ("provider-msg-1", "provider-msg-2"):
        handle_inbound(CTX, {"id": provider_id, "content_ref": "text:yes"}, calls.append, channel=world.channel,
                       store=world.store, clock=world.clock)
    assert len(calls) == 2, "texto igual não prova duplicata"


@conformance("K13", invariants=("N13",), scope="real_mechanism")
def test_k13_two_workers_same_version_one_wins_the_other_does_not_repeat():
    """Simulado nos falsos. A prova de verdade é do adaptador, no mecanismo de concorrência dele."""
    world, episode = _world_with_episode()
    seen_by_both = world.store.load_episode(CTX, "ep-1")
    handed = EpisodeEvent(kind="command_handed_off", at=world.clock.now(), cause_id="decision-1", wait=WAIT)

    def effects(new):
        return (), (WorkItem(work_id=f"execute:{new.cause_id}", kind="execute", payload={}, due_at=new.occurred_at),)

    first = advance(CTX, "ep-1", handed, store=world.store, clock=world.clock, effects=effects, loaded=seen_by_both)
    second = advance(CTX, "ep-1", handed, store=world.store, clock=world.clock, effects=effects,
                     loaded=seen_by_both)
    assert first.outcome == "applied" and first.episode.state == "waiting_effect"
    assert second.outcome == "superseded", "o perdedor repetiu a decisão"
    assert second.episode.version == first.episode.version  # recarregou o estado do vencedor
    assert len(world.store.outbox) == 1, "o efeito foi enfileirado duas vezes"


def test_conflict_that_still_applies_is_retried_on_the_new_state():
    world, episode = _world_with_episode()
    world.faults.arm("commit_transition", Fault.VERSION_CONFLICT)
    asked = EpisodeEvent(kind="question_sent", at=world.clock.now(), cause_id="decision-2", wait=WAIT)
    result = advance(CTX, "ep-1", asked, store=world.store, clock=world.clock)
    assert (result.outcome, result.attempts, result.episode.state) == ("applied", 2, "waiting_input")


@conformance("K29", invariants=("N06",), scope="core")
def test_k29_yes_after_staff_returns_the_conversation_is_not_read_against_the_old_question():
    world, episode = _world_with_episode()
    dialogue = ask({}, question_id="q-1", need_id="n1", epoch=episode.ownership.epoch)
    assert answer_refers_to(dialogue, episode.ownership.epoch) == "q-1"  # antes da devolução, vale

    at = world.clock.advance(60)
    handed = transition(episode, EpisodeEvent(kind="handoff_requested", at=at, cause_id="c1", wait=WAIT),
                        expected_version=1, record_id="r2")
    accepted = transition(handed, EpisodeEvent(kind="handoff_accepted", at=at, cause_id="c2", holder_ref="staff-1"),
                          expected_version=2, record_id="r3")
    returned = transition(accepted, EpisodeEvent(kind="returned", at=at, cause_id="c3"), expected_version=3,
                          record_id="r4")
    # Mesmo que ninguém limpe a pergunta, a época mudou: o "sim" não se liga a ela.
    assert answer_refers_to(dialogue, returned.ownership.epoch) is None
    # E a devolução limpa a pergunta no ar.
    assert answer_refers_to(on_conversation_returned(dialogue), returned.ownership.epoch) is None
