from __future__ import annotations

from conversational_commerce.contracts import Producer
from conversational_commerce.engine import Engine, Ports
from conversational_commerce.profile.test_profile import build_test_profile
from conversational_commerce.testing.fakes import FakeWorld
from conversational_commerce.testing.journeys import j5, j6
from conversational_commerce.testing.journeys.runner import ScriptedModel, script_of
from conversational_commerce.tests.engine.helpers import WITH_MODEL

CTX = j6.CTX
PRODUCER = Producer(name="test", version="1")
NOW = "2026-01-05T09:00:00.000000Z"


def engine(*, steps=(*j6.STEPS, *j5.STEPS), world=None, **profile_overrides):
    world = world or FakeWorld()
    ports = Ports.from_world(world)
    ports.model = ScriptedModel(world.clock, script_of(steps))
    return Engine(ports, build_test_profile(**{**WITH_MODEL, **profile_overrides})), world


def record(n, at=NOW, **extra):
    return {"id": f"rec-{n}", "tenant": "tenant-a", "environment": "test", "trace_id": "trace-1", "occurred_at": at,
            "producer": PRODUCER, **extra}
