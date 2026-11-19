from __future__ import annotations

from conversational_commerce.engine import Engine, Ports
from conversational_commerce.profile.test_profile import build_test_profile
from conversational_commerce.testing.fakes import FakeWorld
from conversational_commerce.testing.journeys import j3, j5
from conversational_commerce.testing.journeys.runner import ScriptedModel, script_of
from conversational_commerce.tests.engine.helpers import WITH_MODEL

CTX = j3.CTX


def engine(*, steps=(*j3.STEPS, *j5.STEPS), world=None, **profile_overrides):
    world = world or FakeWorld()
    ports = Ports.from_world(world)
    ports.model = ScriptedModel(world.clock, script_of(steps))
    return Engine(ports, build_test_profile(**{**WITH_MODEL, **profile_overrides})), world


def only_open(engine):
    (entry,) = engine.commitments.open_entries(CTX.tenant, CTX.environment)
    return entry
