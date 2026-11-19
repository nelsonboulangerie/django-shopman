"""O executor do contrato de efeito sobre o Shopman, provado no PostgreSQL (N6).

O executor (``shopman/shop/conversational/commerce_execute.py``) é a unidade atômica: chave de
idempotência, trava do sítio, guarda do ponto de efeito, efeito e recibo numa transação do
banco. Os testes K do framework que pedem o mecanismo real rodam aqui, com conexões
independentes e um sítio de teste que grava numa ``Session`` de verdade (o efeito conta
``data["applied"]``). O sítio da Concierge (os quatro efeitos) é ``storefront``, e o ``shop``
não o importa; ele tem teste próprio.

| K | O que se prova |
|---|---|
| K08 | resposta perdida, mesma chave e mesmo conteúdo: um efeito, e a reconciliação acha o sucesso |
| K09 | mesma chave, outro conteúdo: ``idempotency_conflict``, recibo como estava |
| K10 | a saída da transação cai depois do efeito: o recibo gravado é achado, nada se repete |
| K11 | posse revogada antes do ponto de efeito: recibo de recusa, nenhum efeito |
| K12 | transferência depois da submissão: reconciliado com a mesma chave, nada se desfaz |
| K14 | dois trabalhadores, a mesma chave: o segundo espera e não repete |
| K15 | a concessão vence entre a decisão e a execução: recusada no ponto de efeito |
| K16 | sem recibo, a reconciliação sela a chave: execução atrasada nunca acontece |
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

import pytest
from conversational_commerce.authority import CoreEffectGuard, Revocations, build_command, issue_line_grant
from conversational_commerce.contracts import IdentityEvidence, Producer
from conversational_commerce.contracts.errors import ErrorCode
from conversational_commerce.ports import PortError, TrustedContext
from conversational_commerce.profile.test_profile import build_test_profile
from conversational_commerce.testing.conformance import conformance
from conversational_commerce.testing.fakes.clock import FakeClock
from django.db import connection, connections, transaction
from shopman.orderman.models import Session

from shopman.shop.conversational.commerce_execute import Done, Reading, ShopmanCommerceExecute

requires_postgres = pytest.mark.skipif(connection.vendor != "postgresql",
                                       reason="Requires PostgreSQL independent connections")
pytestmark = [pytest.mark.django_db(transaction=True), requires_postgres]

CTX = TrustedContext(tenant="nelson-boulangerie", environment="test", subject="conversation:1")
CART = "sess-cc"
PROFILE = build_test_profile()
EVIDENCE = (IdentityEvidence(kind="adapter_login", ref="customer-1", assurance="weak_verified"),)


@dataclass
class SessionSite:
    """O sítio de teste: trava a ``Session``, lê a época de posse dela e conta o efeito."""

    actions: tuple[str, ...] = ("change_cart",)
    entered: threading.Event | None = None
    release: threading.Event | None = None
    refuse: bool = False
    after_commit_raises: bool = False

    def lock(self, ctx, command) -> Reading:
        session = Session.objects.select_for_update().filter(session_key=command.targets[0]).first()
        if session is None:
            raise PortError(ErrorCode.OBJECT_FORBIDDEN, "sacola de outro sujeito")
        return Reading(ownership_epoch=int((session.data or {}).get("epoch", 0)), versions={})

    def apply(self, ctx, command) -> Done:
        if self.entered is not None:
            self.entered.set()
            assert self.release.wait(10), "o ensaio não liberou o primeiro trabalhador"
        session = Session.objects.select_for_update().get(session_key=command.targets[0])
        session.data = {**(session.data or {}), "applied": int((session.data or {}).get("applied", 0)) + 1}
        session.save(update_fields=["data"])
        if self.after_commit_raises:
            transaction.on_commit(lambda: (_ for _ in ()).throw(RuntimeError("a resposta se perdeu")))
        if self.refuse:
            return Done(False, refusal=ErrorCode.REVISION_CONFLICT.value)
        return Done(True, domain_refs={"cart": command.targets[0]})


def applied() -> int:
    return int((Session.objects.get(session_key=CART).data or {}).get("applied", 0))


def set_epoch(epoch: int) -> None:
    session = Session.objects.get(session_key=CART)
    session.data = {**(session.data or {}), "epoch": epoch}
    session.save(update_fields=["data"])


@pytest.fixture
def world():
    Session.objects.create(session_key=CART, channel_ref="whatsapp", data={"epoch": 0})
    clock = FakeClock()

    def record(prefix):
        return {"id": clock.new_id(prefix), "tenant": CTX.tenant, "environment": CTX.environment,
                "trace_id": "trace-n6", "occurred_at": clock.now(), "producer": Producer(name="n6-test", version="1"),
                "episode_id": "ep-n6"}

    def command(parameters=None, epoch=0):
        grant = issue_line_grant(record=record("grant"), grant_id=clock.new_id("grantid"), subject="customer-1",
                                 action="change_cart", targets=(CART,), identity_evidence=EVIDENCE, profile=PROFILE,
                                 now=clock.now())
        cmd = build_command(record=record("cmd"), command_id=clock.new_id("command"), decision_id="dec-1",
                            grant=grant, parameters=parameters or {"item": "ITEM-A", "quantity": "2"},
                            expected_versions={}, ownership_epoch=epoch, scope=CTX.tenant, now=clock.now())
        return grant, cmd

    return clock, command


def execute(executor, grant, cmd, revocations=None):
    try:
        return executor.execute(CTX, cmd, CoreEffectGuard(grant, cmd, revocations or Revocations()))
    finally:
        connections.close_all()


@conformance("K08", invariants=("N08",), scope="adapter")
def test_k08_lost_response_same_key_one_effect_and_reconcile_finds_success(world):
    clock, command = world
    executor = ShopmanCommerceExecute(site=SessionSite(), clock=clock)
    grant, cmd = command()
    first = execute(executor, grant, cmd)  # o chamador "perde" esta resposta
    again = execute(executor, grant, cmd)
    assert first.status == again.status == "success" and again.id == first.id
    assert applied() == 1
    found = executor.reconcile(CTX, cmd)
    assert found.status == "success" and found.supersedes == first.id and applied() == 1
    assert executor.locate(CTX, cmd.idempotency.scope, cmd.idempotency.key).id == first.id


@conformance("K09", invariants=("N08",), scope="adapter")
def test_k09_same_key_other_content_is_conflict_and_the_receipt_stays(world):
    clock, command = world
    executor = ShopmanCommerceExecute(site=SessionSite(), clock=clock)
    grant, cmd = command()
    first = execute(executor, grant, cmd)
    import dataclasses

    other_grant, other = command(parameters={"item": "ITEM-A", "quantity": "5"})
    assert other.content_hash != cmd.content_hash
    reused = dataclasses.replace(other, idempotency=cmd.idempotency)  # a mesma chave, outro conteúdo
    with pytest.raises(PortError) as conflict:
        execute(executor, other_grant, reused)
    assert conflict.value.code == ErrorCode.IDEMPOTENCY_CONFLICT
    assert executor.locate(CTX, cmd.idempotency.scope, cmd.idempotency.key).id == first.id and applied() == 1


@conformance("K10", invariants=("N09",), scope="adapter")
def test_k10_exit_fails_after_the_effect_the_stored_receipt_is_found(world):
    clock, command = world
    executor = ShopmanCommerceExecute(site=SessionSite(after_commit_raises=True), clock=clock)
    grant, cmd = command()
    receipt = execute(executor, grant, cmd)
    assert receipt.status == "success" and applied() == 1
    reconciled = executor.reconcile(CTX, cmd)
    assert reconciled.status == "success" and reconciled.domain_refs == receipt.domain_refs and applied() == 1


@conformance("K11", invariants=("N07", "N10"), scope="real_mechanism")
def test_k11_ownership_revoked_before_the_effect_point_refuses_without_effect(world):
    clock, command = world
    executor = ShopmanCommerceExecute(site=SessionSite(), clock=clock)
    grant, cmd = command(epoch=0)
    set_epoch(1)  # a conversa mudou de dono entre a decisão e o ponto de efeito
    receipt = execute(executor, grant, cmd)
    assert (receipt.status, receipt.effect, receipt.error.code) == ("failure", "not_applied", "authority_revoked")
    assert applied() == 0
    revoked_grant, revoked_cmd = command(parameters={"item": "ITEM-B", "quantity": "1"}, epoch=1)
    revocations = Revocations()
    revocations.revoke(revoked_grant.grant_id, clock.now())
    assert execute(executor, revoked_grant, revoked_cmd, revocations).error.code == "authority_revoked"
    assert applied() == 0


@conformance("K12", invariants=("N10",), scope="real_mechanism")
def test_k12_handoff_after_submission_is_reconciled_and_nothing_is_undone(world):
    clock, command = world
    executor = ShopmanCommerceExecute(site=SessionSite(), clock=clock)
    grant, cmd = command()
    receipt = execute(executor, grant, cmd)
    set_epoch(1)  # a transferência chegou depois do efeito
    reconciled = executor.reconcile(CTX, cmd)
    assert reconciled.status == "success" and reconciled.supersedes == receipt.id and applied() == 1


@conformance("K14", invariants=("N13",), scope="real_mechanism")
def test_k14_two_workers_same_key_the_second_waits_and_never_repeats(world):
    clock, command = world
    entered, release = threading.Event(), threading.Event()
    grant, cmd = command()
    slow = ShopmanCommerceExecute(site=SessionSite(entered=entered, release=release), clock=clock)
    fast = ShopmanCommerceExecute(site=SessionSite(), clock=clock)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(execute, slow, grant, cmd)
        assert entered.wait(10), "o primeiro trabalhador não chegou ao efeito"
        second = pool.submit(execute, fast, grant, cmd)
        release.set()
        receipts = [first.result(timeout=20), second.result(timeout=20)]
    assert {r.status for r in receipts} == {"success"} and receipts[0].id == receipts[1].id
    assert applied() == 1


@conformance("K15", invariants=("N07",), scope="adapter")
def test_k15_grant_expires_between_decision_and_execution(world):
    clock, command = world
    executor = ShopmanCommerceExecute(site=SessionSite(), clock=clock)
    grant, cmd = command()
    clock.advance(11 * 60)  # a concessão da linha vale 10 minutos no perfil de teste
    receipt = execute(executor, grant, cmd)
    assert (receipt.status, receipt.error.code) == ("failure", "grant_expired") and applied() == 0


@conformance("K16", invariants=("N09",), scope="adapter")
def test_k16_reconcile_without_receipt_seals_the_key_and_a_late_execution_never_runs(world):
    clock, command = world
    executor = ShopmanCommerceExecute(site=SessionSite(), clock=clock)
    grant, cmd = command()
    assert executor.locate(CTX, cmd.idempotency.scope, cmd.idempotency.key) is None
    sealed = executor.reconcile(CTX, cmd)
    assert (sealed.status, sealed.effect) == ("failure", "not_applied")
    late = execute(executor, grant, cmd)  # o trabalhador atrasado chega depois do selo
    assert late.status == "failure" and late.id == sealed.id and applied() == 0


def test_a_refused_effect_leaves_nothing_and_is_a_receipt(world):
    clock, command = world
    executor = ShopmanCommerceExecute(site=SessionSite(refuse=True), clock=clock)
    grant, cmd = command()
    receipt = execute(executor, grant, cmd)
    assert (receipt.status, receipt.error.code, receipt.error.retry) == ("failure", "revision_conflict", "never")
    assert applied() == 0  # o efeito recusado voltou ao ponto de salvamento


def test_the_executor_refuses_to_run_inside_another_transaction(world):
    clock, command = world
    executor = ShopmanCommerceExecute(site=SessionSite(), clock=clock)
    grant, cmd = command()
    with transaction.atomic(), pytest.raises(RuntimeError):
        executor.execute(CTX, cmd, CoreEffectGuard(grant, cmd))
    assert applied() == 0


def test_other_tenant_and_unknown_action_are_refused_before_anything(world):
    clock, command = world
    executor = ShopmanCommerceExecute(site=SessionSite(actions=("commit_order",)), clock=clock)
    grant, cmd = command()
    with pytest.raises(PortError) as missing:
        execute(executor, grant, cmd)
    assert missing.value.code == ErrorCode.CAPABILITY_MISSING
    stranger = TrustedContext(tenant="other", environment="test", subject="conversation:1")
    with pytest.raises(PortError) as forbidden:
        ShopmanCommerceExecute(site=SessionSite(), clock=clock).execute(stranger, cmd, CoreEffectGuard(grant, cmd))
    assert forbidden.value.code == ErrorCode.OBJECT_FORBIDDEN and applied() == 0


class SkipsTheGuard(ShopmanCommerceExecute):
    """O executor errado: faz o efeito sem chamar a guarda. Serve só para provar que o K11 o pega."""

    def _effect_unit(self, ctx, command, guard):
        self.site.lock(ctx, command)
        done = self.site.apply(ctx, command)
        receipt = self._receipt(ctx, command, status="success", effect="applied", domain_refs=dict(done.domain_refs))
        from shopman.shop.conversational.commerce_execute import APPLIED, _body

        return _body(command, receipt), APPLIED


def test_the_k11_check_catches_an_executor_that_skips_the_guard(world):
    """O teste do teste: sem a guarda, a posse revogada não impede o efeito, e a asserção do K11 cai."""
    clock, command = world
    grant, cmd = command(epoch=0)
    set_epoch(1)
    receipt = execute(SkipsTheGuard(site=SessionSite(), clock=clock), grant, cmd)
    assert receipt.status == "success" and applied() == 1  # o que o K11 reprova no executor de verdade
