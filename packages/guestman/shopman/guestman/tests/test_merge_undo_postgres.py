"""PostgreSQL proof that a merge audit can be undone only once."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Event, Lock

import pytest
from django.db import close_old_connections, connection, connections
from shopman.guestman.contrib.merge.models import MergeAudit
from shopman.guestman.contrib.merge.service import MergeService
from shopman.guestman.exceptions import CustomerError
from shopman.guestman.models import Customer, PriceTier

requires_postgres = pytest.mark.skipif(
    connection.vendor != "postgresql",
    reason="Requires independent PostgreSQL connections and row locks",
)

pytestmark = [pytest.mark.django_db(transaction=True), requires_postgres]


def _undo(audit_id: str, actor: str, started: Event) -> str:
    close_old_connections()
    started.set()
    try:
        MergeService.undo(audit_id, actor=actor)
        return "ok"
    except CustomerError as exc:
        return str(exc)
    finally:
        connections.close_all()


def test_concurrent_undo_has_one_winner_and_preserves_its_actor(monkeypatch):
    tier = PriceTier.objects.create(ref="regular", name="Regular", is_default=True)
    source = Customer.objects.create(ref="SRC-RACE", first_name="Doador", price_tier=tier)
    target = Customer.objects.create(ref="TGT-RACE", first_name="Destino", price_tier=tier)
    result = MergeService.merge(source, target, {"staff_override": True}, actor="merge")

    first_inside = Event()
    release_first = Event()
    choose_first = Lock()
    chosen = False
    original_restore = MergeService._restore_identity_gaps

    def block_first(cls, source, target, snapshot):
        nonlocal chosen
        with choose_first:
            should_block = not chosen
            chosen = True
        if should_block:
            first_inside.set()
            assert release_first.wait(10)
        return original_restore(source, target, snapshot)

    monkeypatch.setattr(MergeService, "_restore_identity_gaps", classmethod(block_first))

    first_started, second_started = Event(), Event()
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(_undo, result.audit_id, "first", first_started)
        assert first_started.wait(10)
        assert first_inside.wait(10)
        second = pool.submit(_undo, result.audit_id, "second", second_started)
        assert second_started.wait(10)
        release_first.set()
        outcomes = [first.result(20), second.result(20)]

    assert outcomes.count("ok") == 1
    assert sum("already reverted" in outcome for outcome in outcomes) == 1
    audit = MergeAudit.objects.get(pk=result.audit_id)
    assert audit.reverted_by == "first"
