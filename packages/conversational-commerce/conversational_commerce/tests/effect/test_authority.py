"""Concessão, guarda do ponto de efeito e comando: K03, K06, K07, K11, K15."""

from __future__ import annotations

import pytest

from conversational_commerce.authority import CoreEffectGuard, GrantRefused, Revocations, issue_line_grant
from conversational_commerce.contracts import parse_document
from conversational_commerce.ports import EffectState, PortError
from conversational_commerce.testing.conformance import conformance
from conversational_commerce.testing.fakes import FakeCommerceExecute, FakeWorld, Fault

from .helpers import CTX, Bench, record


def test_grant_is_bound_to_the_terms_and_lives_no_longer_than_the_line():
    bench = Bench.make()
    grant = bench.grant()
    assert grant.terms_hash == bench.terms.hash and grant.basis == "customer_confirmation"
    assert grant.confirmation_evidence.after_terms is True
    assert grant.valid_until == bench.world.clock.at(600)  # grant.validity_seconds do perfil de teste
    assert parse_document(grant.to_document()) == grant


def test_grant_needs_the_validity_line():
    lines = tuple(line for line in Bench.make().profile.lines if line.id != "grant.validity_seconds")
    bench = Bench.make(lines=lines)
    with pytest.raises(GrantRefused) as refused:
        bench.grant()
    assert refused.value.code == "profile_line_absent"


@conformance("K03", invariants=("N06", "N12"), scope="adapter")
def test_k03_confirmation_before_the_terms_does_not_authorize():
    bench = Bench.make()
    with pytest.raises(GrantRefused) as refused:
        bench.grant(occurred_at=bench.offer.presented_at)  # mesmo instante: não é posterior
    assert refused.value.code == "confirmation_before_terms"
    assert bench.world.commerce_execute.effects == 0


@conformance("K06", invariants=("N06", "N11"), scope="adapter")
def test_k06_confirmation_from_another_subject_tenant_or_environment():
    bench = Bench.make()
    for changes, code in (({"subject_ref": "customer-2"}, "confirmation_from_other_subject"),
                          ({"subject_ref": None}, "confirmation_from_other_subject"),
                          ({"tenant": "tenant-b"}, "object_forbidden"),
                          ({"environment": "shadow"}, "object_forbidden")):
        with pytest.raises(GrantRefused) as refused:
            bench.grant(**changes)
        assert refused.value.code == code
    # Nada do pedido é revelado a quem não é o dono: a cotação do carrinho alheio é recusada.
    other = CTX.__class__(tenant=CTX.tenant, environment=CTX.environment, subject="customer-2")
    with pytest.raises(PortError) as forbidden:
        bench.world.commerce_read.quote(other, "cart-1")
    assert forbidden.value.code.value == "object_forbidden"


def test_unstable_event_identity_epoch_and_expired_terms_do_not_authorize():
    bench = Bench.make()
    for changes, code in (({"event_assurance": "none"}, "event_identity_unstable"),
                          ({"epoch": 1}, "authority_revoked"),
                          ({"identity_evidence": ()}, "identity_insufficient")):
        with pytest.raises(GrantRefused) as refused:
            bench.grant(**changes)
        assert refused.value.code == code
    bench.world.clock.advance(1800)
    with pytest.raises(GrantRefused) as expired:
        bench.grant()
    assert expired.value.code == "terms_expired"


@conformance("K07", invariants=("N07",), scope="adapter")
def test_k07_price_changes_after_the_confirmation():
    world = FakeWorld()
    world.faults.arm("quote", Fault.PRICE_CHANGES_AFTER_QUOTE)
    bench = Bench.make(world)
    grant = bench.grant()
    command = bench.command(grant)
    receipt = world.commerce_execute.execute(CTX, command, bench.guard(grant, command))
    assert (receipt.status, receipt.effect, receipt.error.code) == ("failure", "not_applied", "terms_changed")
    assert world.state.orders == {} and world.commerce_execute.effects == 0
    # Termos novos são outro documento, com outro hash: pedem confirmação nova.
    assert world.commerce_read.quote(CTX, "cart-1").hash != bench.terms.hash


def _k11(executor_class) -> list[str]:
    """K11: revogação vence antes do ponto de efeito. Devolve o que deu errado (vazio é verde)."""
    world = FakeWorld()
    executor = executor_class(world.clock, world.faults, world.state)
    bench = Bench.make(world)
    grant = bench.grant()
    command = bench.command(grant)
    revocations = Revocations()
    revocations.revoke(grant.grant_id, world.clock.now())
    receipt = executor.execute(CTX, command, CoreEffectGuard(grant, command, revocations))
    problems = []
    if executor.effects or world.state.orders:
        problems.append("houve efeito depois da revogação")
    if (receipt.status, receipt.effect) != ("failure", "not_applied"):
        problems.append(f"recibo {receipt.status}/{receipt.effect}")
    elif receipt.error.code != "authority_revoked":
        problems.append(f"recusa {receipt.error.code}")
    return problems


class ExecutorThatSkipsTheGuard(FakeCommerceExecute):
    """Executor errado de propósito: não chama a guarda no ponto de efeito."""

    def execute(self, ctx, command, guard):
        class Allow:
            def verify(self, state):
                return None

        return super().execute(ctx, command, Allow())


@conformance("K11", invariants=("N07", "N10"), scope="real_mechanism")
def test_k11_revocation_wins_before_the_effect_point():
    assert _k11(FakeCommerceExecute) == []


def test_k11_fails_against_an_executor_that_skips_the_guard():
    """O teste do teste: o K11 reprova o executor que não chama a guarda."""
    assert "houve efeito depois da revogação" in _k11(ExecutorThatSkipsTheGuard)


def test_k11_ownership_change_also_revokes():
    world = FakeWorld()
    bench = Bench.make(world)
    grant = bench.grant()
    command = bench.command(grant)
    world.commerce_execute.epochs[command.episode_id] = 1  # a pessoa assumiu depois da decisão
    receipt = world.commerce_execute.execute(CTX, command, bench.guard(grant, command))
    assert receipt.error.code == "authority_revoked" and world.commerce_execute.effects == 0


@conformance("K15", invariants=("N07",), scope="adapter")
def test_k15_grant_expires_between_decision_and_execution():
    world = FakeWorld()
    bench = Bench.make(world)
    grant = bench.grant()
    command = bench.command(grant)
    world.clock.advance(601)
    receipt = world.commerce_execute.execute(CTX, command, bench.guard(grant, command))
    assert receipt.error.code == "grant_expired" and world.commerce_execute.effects == 0


def test_guard_refuses_a_changed_version():
    bench = Bench.make()
    grant = bench.grant()
    command = bench.command(grant)
    guard = bench.guard(grant, command)
    with pytest.raises(PortError) as conflict:
        guard.verify(EffectState(now=bench.world.clock.now(), terms_hash=bench.terms.hash, versions={"cart-1": 9},
                                 ownership_epoch=0))
    assert conflict.value.code.value == "revision_conflict"
    guard.verify(EffectState(now=bench.world.clock.now(), terms_hash=bench.terms.hash, versions={"cart-1": 1},
                             ownership_epoch=0))
    assert len(guard.seen) == 2


def test_guard_refuses_a_command_outside_its_grant():
    bench = Bench.make()
    grant = bench.grant()
    other = issue_line_grant(record=record(bench.world, "grant"), grant_id="g-other", subject="customer-1",
                             action="change_cart", targets=("cart-1",), identity_evidence=grant.identity_evidence,
                             profile=bench.profile, now=bench.world.clock.now())
    with pytest.raises(ValueError):
        CoreEffectGuard(other, bench.command(grant))


def test_idempotency_key_is_stable_for_the_same_request():
    bench = Bench.make()
    grant = bench.grant()
    first, again = bench.command(grant), bench.command(grant)
    assert first.command_id != again.command_id
    assert first.idempotency == again.idempotency and first.content_hash == again.content_hash
