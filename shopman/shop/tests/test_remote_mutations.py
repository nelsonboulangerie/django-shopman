from __future__ import annotations

from types import SimpleNamespace

import pytest

from shopman.shop.services import remote_mutations

pytestmark = pytest.mark.django_db


def test_run_idempotent_mutation_replays_cached_response():
    calls = 0

    def execute():
        nonlocal calls
        calls += 1
        return {"ok": True, "calls": calls}, 200

    first = remote_mutations.run_idempotent_mutation(
        scope="remote-test",
        key="same-key",
        execute=execute,
    )
    second = remote_mutations.run_idempotent_mutation(
        scope="remote-test",
        key="same-key",
        execute=execute,
    )

    assert first.response_body == {"ok": True, "calls": 1}
    assert first.replayed is False
    assert second.response_body == {"ok": True, "calls": 1}
    assert second.replayed is True
    assert calls == 1


def test_idempotency_key_from_request_prefers_header_then_body_then_fallback():
    header_request = SimpleNamespace(
        headers={"Idempotency-Key": "header-key"},
        data={"idempotency_key": "body-key"},
    )
    body_request = SimpleNamespace(headers={}, data={"idempotency_key": "body-key"})
    fallback_request = SimpleNamespace(headers={}, data={})

    with pytest.raises(remote_mutations.RemoteMutationConflict):
        remote_mutations.idempotency_key_from_request(header_request, fallback="fallback")
    assert remote_mutations.idempotency_key_from_request(body_request, fallback="fallback") == "body-key"
    assert remote_mutations.idempotency_key_from_request(fallback_request, fallback="fallback") == "fallback"


def test_run_idempotent_mutation_can_skip_caching_precondition_failures():
    calls = 0

    def execute():
        nonlocal calls
        calls += 1
        return {"ok": False, "calls": calls}, 409

    first = remote_mutations.run_idempotent_mutation(
        scope="remote-test-no-cache",
        key="same-key",
        execute=execute,
        cache_response=lambda _body, code: code < 400,
    )
    second = remote_mutations.run_idempotent_mutation(
        scope="remote-test-no-cache",
        key="same-key",
        execute=execute,
        cache_response=lambda _body, code: code < 400,
    )

    assert first.response_body == {"ok": False, "calls": 1}
    assert second.response_body == {"ok": False, "calls": 2}
    assert second.replayed is False
    assert calls == 2


def test_idempotency_key_from_request_hashes_overlong_values():
    request = SimpleNamespace(headers={"Idempotency-Key": "x" * 200}, data={})

    key = remote_mutations.idempotency_key_from_request(request, fallback="fallback")

    assert key.startswith("sha256:")
    assert len(key) <= 128


@pytest.mark.parametrize("code", [400, 409, 500])
def test_local_refusal_rolls_back_effects(code):
    from shopman.orderman.models import Order

    def execute():
        Order.objects.create(ref="ATOMIC-REFUSAL")
        return {"detail": "Refused"}, code

    result = remote_mutations.run_idempotent_mutation(scope="local-refusal", key="intent", fingerprint="one", execute=execute)
    assert result.response_code == code
    assert not Order.objects.filter(ref="ATOMIC-REFUSAL").exists()
    receipt = remote_mutations.lookup_local_mutation(scope="local-refusal", key="intent")
    assert (receipt is None) == (code >= 500)


def test_local_receipt_failure_rolls_back_effect_and_enqueue(monkeypatch):
    from shopman.orderman.models import Directive, IdempotencyKey, Order

    save = IdempotencyKey.save

    def fail_receipt(instance, *args, **kwargs):
        if instance.status == "done":
            raise RuntimeError("receipt storage unavailable")
        return save(instance, *args, **kwargs)

    monkeypatch.setattr(IdempotencyKey, "save", fail_receipt)

    def execute():
        order = Order.objects.create(ref="ATOMIC-RECEIPT")
        order.emit_event("local.accepted")
        Directive.objects.create(topic="lab.local", payload={"order_ref": order.ref})
        return {"ref": order.ref}, 200

    with pytest.raises(RuntimeError, match="receipt storage"):
        remote_mutations.run_idempotent_mutation(scope="local-receipt", key="intent", fingerprint="one", execute=execute)
    assert not Order.objects.filter(ref="ATOMIC-RECEIPT").exists()
    assert not Directive.objects.filter(topic="lab.local").exists()
    assert remote_mutations.lookup_local_mutation(scope="local-receipt", key="intent") is None


def test_local_lost_response_replays_without_effect_and_rejects_different_payload():
    from shopman.orderman.models import Order

    def execute():
        order = Order.objects.create(ref="ATOMIC-ONCE")
        return {"ref": order.ref, "outcome": "applied"}, 200

    args = {"scope": "local-once", "key": "intent", "fingerprint": "one", "execute": execute}
    first = remote_mutations.run_idempotent_mutation(**args)
    replay = remote_mutations.run_idempotent_mutation(**args)
    assert first.response_body == replay.response_body
    assert replay.replayed
    with pytest.raises(remote_mutations.RemoteMutationConflict):
        remote_mutations.run_idempotent_mutation(**{**args, "fingerprint": "two"})
    assert Order.objects.filter(ref="ATOMIC-ONCE").count() == 1
    assert remote_mutations.lookup_local_mutation(scope="local-once", key="intent").response_body == first.response_body
    assert remote_mutations.lookup_local_mutation(scope="other-actor", key="intent") is None


def test_fingerprint_is_canonical_and_covers_base_and_inputs():
    first = {"version": 1, "base": "accepted", "inputs": {"a": 1, "b": 2}}
    assert remote_mutations.mutation_fingerprint(first) == remote_mutations.mutation_fingerprint({"inputs": {"b": 2, "a": 1}, "base": "accepted", "version": 1})
    assert remote_mutations.mutation_fingerprint(first) != remote_mutations.mutation_fingerprint({**first, "base": "preparing"})


@pytest.mark.django_db(transaction=True)
def test_postgres_two_connections_commit_one_local_intention():
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    from django.db import close_old_connections, connection, connections
    from shopman.orderman.models import Order

    if connection.vendor != "postgresql":
        pytest.skip("Row-lock concurrency requires PostgreSQL")
    barrier = Barrier(2)

    def worker():
        close_old_connections()
        try:
            barrier.wait(timeout=5)

            def execute():
                order = Order.objects.create(ref="TWO-CONNECTIONS")
                return {"ref": order.ref}, 200

            return remote_mutations.run_idempotent_mutation(scope="local-concurrent", key="intent", fingerprint="one", execute=execute)
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: worker(), range(2)))
    assert sorted(result.replayed for result in results) == [False, True]
    assert Order.objects.filter(ref="TWO-CONNECTIONS").count() == 1
