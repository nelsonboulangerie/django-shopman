"""Operational traces must explain commits without copying private command input."""
import hashlib
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from django.contrib.auth.models import Permission, User
from django.db import transaction
from django.urls import reverse
from shopman.orderman.models import Order

from shopman.backstage.tests._order_intent import context_payload
from shopman.shop.logging import JsonLogFormatter
from shopman.shop.models import Shop
from shopman.shop.services.observability import current_operational_context, operational_context, operational_event
from shopman.shop.services.remote_mutations import run_idempotent_mutation


@pytest.fixture(autouse=True)
def capture_operational_logger(caplog):
    # O logger shopman deliberadamente não propaga ao root do pytest.
    target = logging.getLogger("shopman.operational")
    target.addHandler(caplog.handler)
    yield
    target.removeHandler(caplog.handler)


@pytest.fixture
def actor(db):
    Shop.objects.get_or_create(name="Synthetic observation lab")
    user = User.objects.create_user("trace-operator", password="SYNTHETIC-LOGIN", is_staff=True)
    user.user_permissions.add(Permission.objects.get(content_type__app_label="shop", codename="manage_orders"))
    return user


def records(caplog, event=None):
    return [record for record in caplog.records if record.name == "shopman.operational" and (event is None or getattr(record, "event", None) == event)]


@pytest.mark.django_db(transaction=True)
def test_commit_replay_and_receipt_correlate_without_private_input(client, actor, caplog):
    caplog.set_level(logging.INFO, logger="shopman.operational")
    order = Order.objects.create(ref="OBS-ORDER", channel_ref="web", status="accepted", data={"payment": {"method": "cash"}})
    client.force_login(actor)
    body = context_payload(client, order.ref, "notes", notes="SECRET CUSTOMER NOTE")
    body["idempotency_key"] = "SECRET INTENTION TOKEN"
    body["manager_approval"] = {"pin": "SECRET MANAGER PIN"}
    url = reverse("api-backstage-order-notes", args=[order.ref])
    caplog.clear()
    first = client.post(url, body, content_type="application/json")
    second = client.post(url, body, content_type="application/json")
    receipt = client.get(url, {"idempotency_key": body["idempotency_key"]})
    assert first.status_code == second.status_code == receipt.status_code == 200
    assert len({response["X-Request-ID"] for response in (first, second, receipt)}) == 3
    committed = records(caplog, "operator.command.local_result")
    assert len(committed) == 1 and committed[0].outcome == "applied"
    assert committed[0].actor_id == actor.pk
    assert committed[0].resource_ref == order.ref
    assert committed[0].request_id == first["X-Request-ID"]
    assert committed[0].base_revision_digest == hashlib.sha256(body["base_revision"].encode()).hexdigest()
    replays = records(caplog, "operator.command.receipt")
    assert len(replays) == 2 and all(record.replayed for record in replays)
    assert {record.intention_digest for record in committed + replays} == {hashlib.sha256(body["idempotency_key"].encode()).hexdigest()}
    encoded = "\n".join(JsonLogFormatter().format(record) for record in records(caplog))
    assert "SECRET" not in encoded
    assert "notes" not in json.loads(JsonLogFormatter().format(committed[0]))
    assert current_operational_context() == {}


@pytest.mark.django_db(transaction=True)
def test_response_outage_does_not_erase_commit_evidence(client, actor, caplog, monkeypatch):
    caplog.set_level(logging.INFO, logger="shopman.operational")
    order = Order.objects.create(ref="OBS-LOST", channel_ref="web", status="accepted", data={"payment": {"method": "cash"}})
    client.force_login(actor)
    body = context_payload(client, order.ref, "notes", notes="Saved once")
    url = reverse("api-backstage-order-notes", args=[order.ref])
    caplog.clear()
    def unavailable(*args, **kwargs):
        raise RuntimeError("projection outage")
    monkeypatch.setattr("shopman.backstage.api.operations.build_operator_order", unavailable)
    with pytest.raises(RuntimeError, match="projection outage"):
        client.post(url, body, content_type="application/json")
    committed = records(caplog, "operator.command.local_result")
    finished = records(caplog, "operator.request.finished")
    assert committed[0].outcome == "applied"
    assert finished[0].outcome == "transport_unknown"
    assert committed[0].request_id == finished[0].request_id
    order.refresh_from_db()
    assert order.data["kitchen_note"] == "Saved once"
    assert current_operational_context() == {}


@pytest.mark.django_db
def test_permission_denial_never_attributes_an_authorized_actor_or_local_effect(client, caplog):
    caplog.set_level(logging.INFO, logger="shopman.operational")
    response = client.post(reverse("api-backstage-order-notes", args=["OTHER"]), {"expected_actor_id": 123, "notes": "SECRET"}, content_type="application/json")
    assert response.status_code == 403
    finished = records(caplog, "operator.request.finished")
    assert len(finished) == 1 and not hasattr(finished[0], "actor_id")
    assert records(caplog, "operator.command.local_result") == []


@pytest.mark.django_db(transaction=True)
def test_outer_rollback_does_not_emit_a_confirmed_local_result(caplog):
    caplog.set_level(logging.INFO, logger="shopman.operational")
    with operational_context(request_id="rollback-test", operation="test"):
        with pytest.raises(RuntimeError):
            with transaction.atomic():
                run_idempotent_mutation(scope="observation-test", key="once", fingerprint="same", execute=lambda: ({"outcome": "applied"}, 200))
                raise RuntimeError("rollback")
    assert records(caplog, "operator.command.local_result") == []


def test_concurrent_contexts_do_not_cross_people_or_requests(caplog):
    caplog.set_level(logging.INFO, logger="shopman.operational")
    barrier = Barrier(2)
    def emit(actor):
        with operational_context(request_id=f"request-{actor}", actor_id=actor):
            barrier.wait(timeout=5)
            operational_event("observation.test")
        assert current_operational_context() == {}
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(emit, (1, 2)))
    assert {(record.request_id, record.actor_id) for record in records(caplog, "observation.test")} == {("request-1", 1), ("request-2", 2)}
