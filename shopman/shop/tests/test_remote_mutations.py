from __future__ import annotations

from datetime import timedelta
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


def test_run_idempotent_mutation_replays_deterministic_precondition_failure():
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
    assert second.response_body == {"ok": False, "calls": 1}
    assert second.replayed is True
    assert calls == 1


def test_failed_remote_attempt_accepts_corrected_payload_with_same_gesture_key():
    calls = 0

    def reject():
        nonlocal calls
        calls += 1
        return {"ok": False, "calls": calls}, 409

    first = remote_mutations.run_idempotent_mutation(
        scope="remote-corrected",
        key="same-confirmation",
        payload={"notes": "wrong"},
        execute=reject,
        cache_response=lambda body, _code: bool(body.get("ok")),
        in_progress_ttl=timedelta(seconds=30),
        allow_changed_payload_after_rejection=True,
    )
    replay = remote_mutations.run_idempotent_mutation(
        scope="remote-corrected",
        key="same-confirmation",
        payload={"notes": "wrong"},
        execute=reject,
        cache_response=lambda body, _code: bool(body.get("ok")),
        in_progress_ttl=timedelta(seconds=30),
        allow_changed_payload_after_rejection=True,
    )
    second = remote_mutations.run_idempotent_mutation(
        scope="remote-corrected",
        key="same-confirmation",
        payload={"notes": "reviewed"},
        execute=lambda: ({"ok": True}, 200),
        cache_response=lambda body, _code: bool(body.get("ok")),
        in_progress_ttl=timedelta(seconds=30),
        allow_changed_payload_after_rejection=True,
    )

    assert first.response_body == {"ok": False, "calls": 1}
    assert replay.response_body == first.response_body
    assert replay.replayed is True
    assert calls == 1
    assert second.response_body == {"ok": True}
    assert second.replayed is False


def test_ambiguous_remote_failure_preserves_payload_ownership():
    from shopman.orderman.models import IdempotencyKey

    def ambiguous_provider_call():
        raise TimeoutError("provider may already have accepted the charge")

    with pytest.raises(TimeoutError):
        remote_mutations.run_idempotent_mutation(
            scope="remote-ambiguous",
            key="payment-attempt",
            payload={"amount": 3600},
            execute=ambiguous_provider_call,
            in_progress_ttl=timedelta(seconds=30),
            allow_changed_payload_after_rejection=True,
        )

    with pytest.raises(remote_mutations.RemoteMutationConflict):
        remote_mutations.run_idempotent_mutation(
            scope="remote-ambiguous",
            key="payment-attempt",
            payload={"amount": 7200},
            execute=lambda: ({"ok": True}, 200),
            in_progress_ttl=timedelta(seconds=30),
            allow_changed_payload_after_rejection=True,
        )

    receipt = IdempotencyKey.objects.get(scope="remote-ambiguous", key="payment-attempt")
    assert receipt.status == "failed"
    assert receipt.response_code is None
    assert receipt.request_fingerprint == remote_mutations.fingerprint({"amount": 3600})


def test_stale_remote_worker_cannot_overwrite_reclaimed_lease():
    from django.utils import timezone
    from shopman.orderman.models import IdempotencyKey

    replacement_expiry = timezone.now() + timedelta(minutes=10)

    def finish_after_reclaim():
        IdempotencyKey.objects.filter(scope="remote-lease", key="attempt").update(
            expires_at=replacement_expiry,
        )
        return {"ok": True}, 200

    with pytest.raises(remote_mutations.RemoteMutationInProgress, match="lease was reclaimed"):
        remote_mutations.run_idempotent_mutation(
            scope="remote-lease",
            key="attempt",
            payload={"amount": 3600},
            execute=finish_after_reclaim,
            in_progress_ttl=timedelta(seconds=30),
        )

    receipt = IdempotencyKey.objects.get(scope="remote-lease", key="attempt")
    assert receipt.status == "in_progress"
    assert receipt.expires_at == replacement_expiry
    assert receipt.response_body is None


def test_stale_remote_exception_preserves_reclaimed_lease_and_original_error():
    from django.utils import timezone
    from shopman.orderman.models import IdempotencyKey

    replacement_expiry = timezone.now() + timedelta(minutes=10)

    def fail_after_reclaim():
        IdempotencyKey.objects.filter(scope="remote-stale-error", key="attempt").update(
            expires_at=replacement_expiry,
        )
        raise TimeoutError("original provider timeout")

    with pytest.raises(TimeoutError, match="original provider timeout"):
        remote_mutations.run_idempotent_mutation(
            scope="remote-stale-error",
            key="attempt",
            payload={"amount": 3600},
            execute=fail_after_reclaim,
            in_progress_ttl=timedelta(seconds=30),
        )

    receipt = IdempotencyKey.objects.get(scope="remote-stale-error", key="attempt")
    assert receipt.status == "in_progress"
    assert receipt.expires_at == replacement_expiry
    assert receipt.response_code is None
    assert receipt.response_body is None


def test_expired_remote_claim_with_fingerprint_can_resume_after_process_death():
    from django.utils import timezone
    from shopman.orderman.models import IdempotencyKey

    IdempotencyKey.objects.create(
        scope="remote-expired",
        key="crashed-attempt",
        status="in_progress",
        request_fingerprint=remote_mutations.fingerprint({"amount": 3600}),
        expires_at=timezone.now() - timedelta(seconds=1),
    )

    result = remote_mutations.run_idempotent_mutation(
        scope="remote-expired",
        key="crashed-attempt",
        payload={"amount": 3600},
        in_progress_ttl=timedelta(minutes=15),
        execute=lambda: ({"ok": True}, 200),
    )

    assert result.response_body == {"ok": True}
    assert IdempotencyKey.objects.get(scope="remote-expired", key="crashed-attempt").status == "done"


@pytest.mark.parametrize("status", ["failed", "in_progress"])
def test_lookup_allows_failed_or_expired_non_atomic_claim_to_resume(status):
    from django.utils import timezone
    from shopman.orderman.models import IdempotencyKey

    payload = {"amount": 3600}
    IdempotencyKey.objects.create(
        scope="checkout-recovery",
        key=status,
        status=status,
        request_fingerprint=remote_mutations.fingerprint(payload),
        expires_at=timezone.now() - timedelta(seconds=1),
    )

    assert remote_mutations.lookup_idempotent_mutation(
        scope="checkout-recovery",
        key=status,
        payload=payload,
    ) is None


def test_lookup_keeps_a_live_non_atomic_claim_in_progress():
    from django.utils import timezone
    from shopman.orderman.models import IdempotencyKey

    payload = {"amount": 3600}
    IdempotencyKey.objects.create(
        scope="checkout-recovery",
        key="live",
        status="in_progress",
        request_fingerprint=remote_mutations.fingerprint(payload),
        expires_at=timezone.now() + timedelta(minutes=1),
    )

    with pytest.raises(remote_mutations.RemoteMutationInProgress):
        remote_mutations.lookup_idempotent_mutation(
            scope="checkout-recovery",
            key="live",
            payload=payload,
        )


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
