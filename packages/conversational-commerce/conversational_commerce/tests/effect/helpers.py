from __future__ import annotations

import dataclasses

from conversational_commerce.authority import Confirmation, CoreEffectGuard, Offer, build_command, issue_grant
from conversational_commerce.contracts import Producer
from conversational_commerce.engine import Engine, Ports
from conversational_commerce.ledger import ReceiptLedger, Settler
from conversational_commerce.profile.test_profile import build_test_profile
from conversational_commerce.testing.fakes import FakeWorld
from conversational_commerce.testing.journeys import j4
from conversational_commerce.testing.journeys.runner import ScriptedModel, script_of
from conversational_commerce.tests.engine.helpers import WITH_MODEL

CTX = j4.CTX
PRODUCER = Producer(name="test", version="1")
EPISODE = "ep-test"


def engine(*, steps=j4.STEPS, world=None, profile_overrides=None):
    world = world or FakeWorld()
    ports = Ports.from_world(world)
    ports.model = ScriptedModel(world.clock, script_of(steps))
    profile = build_test_profile(**(WITH_MODEL if profile_overrides is None else profile_overrides))
    return Engine(ports, profile, subject_of=j4.subject), world


def record(world, prefix, ctx=CTX):
    return {"id": world.clock.new_id(prefix), "tenant": ctx.tenant, "environment": ctx.environment,
            "trace_id": "trace-test", "occurred_at": world.clock.now(), "producer": PRODUCER, "episode_id": EPISODE}


@dataclasses.dataclass
class Bench:
    """Termos cotados, oferta, confirmação, concessão e comando: o contrato de efeito sem o turno."""

    world: FakeWorld
    profile: object
    terms: object
    offer: Offer

    @classmethod
    def make(cls, world=None, **profile_overrides):
        world = world or FakeWorld()
        terms = world.commerce_read.quote(CTX, "cart-1")
        offer = Offer(terms_hash=terms.hash, terms_id=terms.terms_id, terms_version=terms.version, target="cart-1",
                      subject_ref=terms.recipient.subject_ref, tenant=CTX.tenant, environment=CTX.environment,
                      presented_at=world.clock.now(), valid_until=terms.valid_until, question_id="q-1", epoch=0)
        world.clock.advance(5)
        return cls(world, build_test_profile(**profile_overrides), terms, offer)

    def confirmation(self, **changes) -> Confirmation:
        base = Confirmation(event_id="evt-yes", event_assurance="provider_claimed", occurred_at=self.world.clock.now(),
                            tenant=CTX.tenant, environment=CTX.environment, subject_ref="customer-1", epoch=0,
                            identity_evidence=(j4.VERIFIED,))
        return dataclasses.replace(base, **changes)

    def grant(self, **confirmation_changes):
        return issue_grant(record=record(self.world, "grant"), grant_id=self.world.clock.new_id("grantid"),
                           offer=self.offer, confirmation=self.confirmation(**confirmation_changes),
                           action="commit_order", profile=self.profile, now=self.world.clock.now())

    def command(self, grant, *, parameters=None):
        return build_command(record=record(self.world, "cmd"), command_id=self.world.clock.new_id("command"),
                             decision_id="dec-1", grant=grant, parameters=parameters or {},
                             expected_versions={"cart-1": self.offer.terms_version}, ownership_epoch=0,
                             scope=CTX.tenant, now=self.world.clock.now())

    def guard(self, grant, command, revocations=None):
        return CoreEffectGuard(grant, command, revocations) if revocations else CoreEffectGuard(grant, command)

    def settler(self, executor=None, ledger=None):
        return Settler(ledger or ReceiptLedger(), executor or self.world.commerce_execute, self.world.clock,
                       self.profile)
