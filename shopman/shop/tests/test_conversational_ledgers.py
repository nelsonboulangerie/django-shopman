"""Os livros do motor sobrevivem ao turno (#3198, peça 3a): recibos, memória e exposições.

No N9 o ``Engine`` é montado de novo a cada turno. Aqui o motor roda as jornadas do framework
sobre o armazenamento do Shopman, e um motor NOVO, montado com os livros reconstruídos do
banco, vê o que o primeiro deixou: os comandos e recibos (J4), a memória declarada (J6) e as
exposições, que antes não eram gravadas.
"""

from __future__ import annotations

import dataclasses

import pytest
from conversational_commerce.contracts import ExposureEvent
from conversational_commerce.engine import Engine, Ports
from conversational_commerce.profile.test_profile import build_test_profile
from conversational_commerce.testing.fakes import FakeWorld
from conversational_commerce.testing.journeys import j4, j6, run_journey
from conversational_commerce.testing.journeys.runner import ScriptedModel, script_of

from shopman.shop.conversational.ledgers import (
    DurableExposureLedger,
    exposure_ledger,
    memory_store,
    receipt_ledger,
)
from shopman.shop.conversational.store import ShopmanStore
from shopman.shop.models import ConversationalRecord

pytestmark = pytest.mark.django_db

# O teto do teste do framework, com o leitor roteirizado (o mesmo da conformidade do N8).
WITH_MODEL = {"limits": {"max_steps": 6, "max_seconds": 20, "max_queries": 10, "max_model_calls": 2,
                         "max_spend": {"amount_minor": 0, "currency": "XTS"}}}


def _engine(steps, *, ctx, subject_of=None):
    world = FakeWorld()
    ports = Ports.from_world(world)
    ports.store = ShopmanStore(clock=world.clock)
    ports.model = ScriptedModel(world.clock, script_of(steps))
    extra = {"subject_of": subject_of} if subject_of else {}
    engine = Engine(ports, build_test_profile(**WITH_MODEL), exposures=DurableExposureLedger(ctx=ctx), **extra)
    return engine, world


def test_commands_and_receipts_come_back_in_a_new_turn():
    engine, _ = _engine(j4.STEPS, ctx=j4.CTX, subject_of=j4.subject)
    runs = run_journey(engine, j4.CTX, j4.STEPS)
    assert [run.problems for run in runs] == [()] * len(runs)
    assert engine.ledger.commands, "a J4 executa efeito"

    rebuilt = receipt_ledger(j4.CTX)
    assert set(rebuilt.commands) == set(engine.ledger.commands)
    for command_id in engine.ledger.commands:
        assert rebuilt.latest(command_id) == engine.ledger.latest(command_id)
        assert rebuilt.history(command_id) == engine.ledger.history(command_id)


def test_a_rebuilt_ledger_never_sends_the_same_command_to_execute_again():
    from conversational_commerce.ledger.receipts import next_step

    engine, world = _engine(j4.STEPS, ctx=j4.CTX, subject_of=j4.subject)
    run_journey(engine, j4.CTX, j4.STEPS)
    rebuilt = receipt_ledger(j4.CTX)
    for command in rebuilt.commands.values():
        assert next_step(rebuilt, command, now=world.clock.now(), retention=None, attempt=2) == "done"


def test_declared_memory_comes_back_for_the_same_subject_only():
    ctx = j4.CTX.__class__(tenant=j4.CTX.tenant, environment="test")
    engine, _ = _engine(j6.STEPS, ctx=ctx)
    run_journey(engine, ctx, j6.STEPS)
    assert engine.memory.history, "a J6 declara memória"
    subject = engine.memory.history[0].subject_ref

    rebuilt = memory_store(ctx, subject)
    assert [item.memory_id for item in rebuilt.history] == [item.memory_id for item in engine.memory.history]
    assert memory_store(ctx, "outro-sujeito").history == []


def test_every_exposure_is_written_and_comes_back():
    engine, _ = _engine(j4.STEPS, ctx=j4.CTX, subject_of=j4.subject)
    run_journey(engine, j4.CTX, j4.STEPS)
    sent = engine.exposures.history
    assert sent, "cada resposta enviada vira exposição"
    stored = ConversationalRecord.objects.filter(schema=ExposureEvent.SCHEMA)
    assert stored.count() == len(sent)

    rebuilt = exposure_ledger(j4.CTX)
    assert [e.id for e in rebuilt.history] == [e.id for e in sent]
    rebuilt.record(sent[0])  # o mesmo registro outra vez não duplica, nem no banco
    assert stored.count() == len(sent)


def test_the_ledgers_never_cross_tenant_or_environment():
    engine, _ = _engine(j4.STEPS, ctx=j4.CTX, subject_of=j4.subject)
    run_journey(engine, j4.CTX, j4.STEPS)
    other = dataclasses.replace(j4.CTX, environment="shadow")
    assert receipt_ledger(other).commands == {}
    assert exposure_ledger(other).history == []
