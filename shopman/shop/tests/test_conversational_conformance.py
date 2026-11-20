"""As portas de armazenamento, relógio e resultados do Shopman, provadas no PostgreSQL (N8).

O que se prova aqui, no mecanismo real:

- a checagem de forma do framework (``run_checks``) passa para ``store``, ``clock`` e
  ``outcomes`` com o arnês do Shopman;
- K13: dois trabalhadores, a mesma versão do episódio: um grava, o outro recebe
  ``revision_conflict`` e nada dele entra (estado, registros e caixa de saída);
- K01: a mesma entrada, gravada ao mesmo tempo por dois trabalhadores, entra uma vez;
- a caixa de saída: dois trabalhadores nunca reivindicam o mesmo trabalho; o trabalho de quem
  morreu volta quando a posse vence, com a tentativa somada;
- o núcleo inteiro roda sobre o armazenamento do Shopman: as jornadas J1 e J2 do framework,
  com o episódio, os registros e a caixa de saída no PostgreSQL.
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from conversational_commerce.contracts import Episode, InteractionEvent
from conversational_commerce.engine import Engine, Ports
from conversational_commerce.ports import PortError, Transition, TrustedContext, WorkItem
from conversational_commerce.profile.test_profile import build_test_profile
from conversational_commerce.testing.conformance import conformance
from conversational_commerce.testing.conformance.harness import HarnessEnv, run_checks
from conversational_commerce.testing.fakes import FakeWorld
from conversational_commerce.testing.fakes.clock import FakeClock
from conversational_commerce.testing.journeys import j1, j2
from conversational_commerce.testing.journeys.runner import ScriptedModel, run_journey, script_of
from django.db import connection, connections

from shopman.shop.conversational.clock import ShopmanClock
from shopman.shop.conversational.outcomes import ShopmanOutcomes
from shopman.shop.conversational.store import ShopmanStore
from shopman.shop.models import ConversationalEpisode, ConversationalRecord, ConversationalWork, Shop

requires_postgres = pytest.mark.skipif(connection.vendor != "postgresql",
                                       reason="Requires PostgreSQL independent connections")
pytestmark = [pytest.mark.django_db(transaction=True), requires_postgres]

CTX = TrustedContext(tenant="nelson-boulangerie", environment="test")
PRODUCER = {"name": "n8-test", "version": "1"}


def envelope(clock, prefix, **extra):
    return {"id": clock.new_id(prefix), "tenant": CTX.tenant, "environment": CTX.environment,
            "trace_id": "trace-n8", "occurred_at": clock.now(), "producer": PRODUCER, **extra}


def closing(fn):
    def run(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        finally:
            connections.close_all()
    return run


def test_the_framework_shape_checks_pass_for_store_clock_and_outcomes():
    Shop.objects.create(name="Nelson Boulangerie")
    clock = FakeClock()
    env = HarnessEnv(ctx=CTX, clock=clock, currency="BRL")
    assert run_checks("store", ShopmanStore(clock=clock), env) == []
    assert run_checks("clock", ShopmanClock(CTX), env) == []
    assert run_checks("outcomes", ShopmanOutcomes(clock=clock), env) == []


@conformance("K13", invariants=("N13",), scope="real_mechanism")
def test_k13_two_workers_same_episode_version_one_wins_the_other_writes_nothing():
    clock = FakeClock()
    store = ShopmanStore(clock=clock)
    opened = Episode(**envelope(clock, "eprec", episode_id="ep-k13"), state="active", version=1,
                     ownership={"owner": "automation", "epoch": 0}, opened_at=clock.now())
    store.commit_transition(CTX, Transition(episode=opened, expected_version=0), (), ())
    barrier = threading.Barrier(2)

    @closing
    def worker(name):
        nxt = Episode(**{**envelope(clock, "eprec", episode_id="ep-k13"), "id": f"eprec-{name}"}, state="active",
                      version=2, ownership={"owner": "automation", "epoch": 0}, opened_at=opened.opened_at)
        work = WorkItem(work_id=f"send:{name}", kind="send", payload={}, due_at=clock.now())
        event = InteractionEvent(**envelope(clock, "evt", episode_id="ep-k13"),
                                 channel_binding={"channel": "c", "conversation_ref": name}, actor="customer",
                                 event_identity={"assurance": "none"}, type="message")
        barrier.wait(10)
        try:
            store.commit_transition(CTX, Transition(episode=nxt, expected_version=1), (event,), (work,))
            return name, "won"
        except PortError as error:
            return name, error.code.value

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = dict(pool.map(worker, ["a", "b"]))
    assert sorted(results.values()) == ["revision_conflict", "won"]
    winner = next(name for name, outcome in results.items() if outcome == "won")
    assert ConversationalEpisode.objects.get(episode_id="ep-k13").version == 2
    # Do perdedor, nada entrou: nem registro, nem trabalho.
    assert list(ConversationalWork.objects.values_list("work_id", flat=True)) == [f"send:{winner}"]
    assert ConversationalRecord.objects.filter(schema=InteractionEvent.SCHEMA).count() == 1


@conformance("K01", invariants=("N12",), scope="adapter")
def test_k01_the_same_entry_from_two_workers_is_recorded_once():
    clock = FakeClock()
    store = ShopmanStore(clock=clock)
    barrier = threading.Barrier(2)

    @closing
    def worker(name):
        event = InteractionEvent(**{**envelope(clock, "evt"), "id": f"evt-{name}"},
                                 channel_binding={"channel": "whatsapp", "conversation_ref": "c1"},
                                 actor="customer", event_identity={"id": "provider-1", "assurance": "provider_claimed"},
                                 type="message")
        barrier.wait(10)
        return store.record_event_once(CTX, event)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(worker, ["a", "b"]))
    assert sorted(created for _, created in results) == [False, True]
    assert len({event.id for event, _ in results}) == 1
    assert ConversationalRecord.objects.count() == 1


def test_two_workers_never_claim_the_same_work_and_a_dead_lease_comes_back():
    clock = FakeClock()
    store = ShopmanStore(clock=clock)
    store.schedule(CTX, WorkItem(work_id="w1", kind="send", payload={}, due_at=clock.now()))
    barrier = threading.Barrier(2)

    @closing
    def worker(_):
        barrier.wait(10)
        claim = store.claim_work(CTX, "send", 60)
        return None if claim is None else claim.work.work_id

    with ThreadPoolExecutor(max_workers=2) as pool:
        claims = list(pool.map(worker, [1, 2]))
    assert sorted(c or "" for c in claims) == ["", "w1"]
    clock.advance(61)  # o trabalhador morreu segurando: a posse vence
    again = store.claim_work(CTX, "send", 60)
    assert again is not None and again.work.work_id == "w1" and again.attempt == 2
    store.complete_work(CTX, "w1")
    clock.advance(61)
    assert store.claim_work(CTX, "send", 60) is None


def test_a_tenant_never_reads_another():
    clock = FakeClock()
    store = ShopmanStore(clock=clock)
    episode = Episode(**envelope(clock, "eprec", episode_id="ep-t"), state="active", version=1,
                      ownership={"owner": "automation", "epoch": 0}, opened_at=clock.now())
    store.commit_transition(CTX, Transition(episode=episode, expected_version=0), (), ())
    other = TrustedContext(tenant="outra-loja", environment="test")
    assert store.load_episode(other, "ep-t") is None
    with pytest.raises(PortError) as forbidden:
        store.commit_transition(other, Transition(episode=episode, expected_version=1), (), ())
    assert forbidden.value.code.value == "object_forbidden"


@pytest.mark.parametrize("journey", [j1, j2], ids=["J1", "J2"])
def test_the_core_runs_its_journeys_on_the_shopman_store(journey):
    """O núcleo inteiro sobre o armazenamento do Shopman: episódio, registros e caixa de saída no banco."""
    world = FakeWorld()
    ports = Ports.from_world(world)
    ports.store = ShopmanStore(clock=world.clock)
    ports.model = ScriptedModel(world.clock, script_of(journey.STEPS))
    profile = build_test_profile(limits={"max_steps": 6, "max_seconds": 20, "max_queries": 10,
                                         "max_model_calls": 2, "max_spend": {"amount_minor": 0, "currency": "XTS"}})
    ctx = TrustedContext(tenant=profile.tenant, environment="test")
    runs = run_journey(Engine(ports, profile), ctx, journey.STEPS)
    assert [run.problems for run in runs] == [()] * len(runs)
    episode_id = runs[-1].result.episode.episode_id
    stored = ConversationalEpisode.objects.get(episode_id=episode_id)
    assert stored.version == runs[-1].result.episode.version
    assert ConversationalRecord.objects.filter(episode_id=episode_id).count() > len(runs)
    assert ConversationalWork.objects.filter(kind="send").count() == len(runs)


@conformance("K02", invariants=("N12",), scope="adapter")
def test_k02_two_equal_messages_with_different_identities_are_both_kept():
    """Texto igual não prova duplicata: o que deduplica é a identidade do evento."""
    clock = FakeClock()
    store = ShopmanStore(clock=clock)
    first, second = (InteractionEvent(**envelope(clock, "evt"), channel_binding={"channel": "whatsapp",
                                                                                  "conversation_ref": "c1"},
                                      actor="customer", event_identity={"id": provider, "assurance": "provider_claimed"},
                                      type="message", content_ref="text:sim")
                     for provider in ("provider-1", "provider-2"))
    assert store.record_event_once(CTX, first)[1] is True
    assert store.record_event_once(CTX, second)[1] is True
    assert ConversationalRecord.objects.filter(schema=InteractionEvent.SCHEMA).count() == 2
