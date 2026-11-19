from __future__ import annotations

from conversational_commerce.engine import Engine, Ports
from conversational_commerce.ports import TrustedContext
from conversational_commerce.profile.test_profile import build_test_profile
from conversational_commerce.testing.fakes import FakeWorld
from conversational_commerce.testing.journeys.runner import ScriptedModel, script_of

CTX = TrustedContext(tenant="tenant-a", environment="test")
SHADOW = TrustedContext(tenant="tenant-a", environment="shadow")
# O perfil de teste nunca chama modelo; para exercitar o leitor, um teto pequeno, ainda sem gasto.
WITH_MODEL = {"limits": {"max_steps": 6, "max_seconds": 20, "max_queries": 10, "max_model_calls": 2,
                         "max_spend": {"amount_minor": 0, "currency": "XTS"}}}


def engine(*, steps=(), world=None, profile_overrides=None, model=None, channel=None):
    world = world or FakeWorld()
    ports = Ports.from_world(world)
    if steps:
        ports.model = ScriptedModel(world.clock, script_of(steps))
    if model is not None:
        ports.model = model
    if channel is not None:
        ports.channel = channel
    overrides = WITH_MODEL if profile_overrides is None else profile_overrides
    return Engine(ports, build_test_profile(**overrides)), world


def message(mid: str, text: str, **extra):
    return {"id": mid, "from": "addr-1", "conversation": "conv-1", "content_ref": f"text:{text}", **extra}
