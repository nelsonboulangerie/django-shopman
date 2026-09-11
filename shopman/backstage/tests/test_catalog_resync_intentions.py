"""Resync has a local enqueue receipt, never a claim that the provider received it."""
from uuid import uuid4

import pytest
from shopman.orderman.models import Directive, IdempotencyKey

from shopman.backstage.tests import test_api_catalog_surface as fixtures

catalog = fixtures.catalog
operator = fixtures.operator
shop = fixtures.shop
pytestmark = pytest.mark.django_db(transaction=True)
URL = fixtures.RESYNC_URL


@pytest.fixture(autouse=True)
def isolated_registry(monkeypatch):
    from shopman.offerman import conf

    monkeypatch.setattr(conf, "get_projection_backend_channels", lambda: ["web", "ifood"])
    monkeypatch.setattr(conf, "get_projection_backend", lambda ref: object() if ref in {"web", "ifood"} else None)


def observed(client, operator):
    client.force_login(operator)
    response = client.get(URL, {"sku": "PAO"})
    assert response.status_code == 200
    return {**response.json()["action"]["payload_schema"], "sku": "PAO"}


def test_missing_product_or_target_cannot_claim_queued(client, operator, catalog):
    client.force_login(operator)
    before = Directive.objects.count()
    assert client.post(URL, {"sku": "MISSING", "channel_ref": "ifood"}, content_type="application/json").status_code == 400
    assert Directive.objects.count() == before


def test_replay_after_worker_completion_does_not_enqueue_again(client, operator, catalog):
    body = observed(client, operator)
    key = str(uuid4())
    first = client.post(URL, body, content_type="application/json", HTTP_IDEMPOTENCY_KEY=key)
    assert first.status_code == 200
    assert first.json()["outcome"] == "applied"
    tasks = first.json()["tasks"]
    assert len(tasks) == 2
    ids = [task["directive_id"] for task in tasks]
    Directive.objects.filter(pk__in=ids).update(status="done")
    before = Directive.objects.count()
    replay = client.post(URL, body, content_type="application/json", HTTP_IDEMPOTENCY_KEY=key)
    assert replay.json() == client.get(URL, {"sku": "PAO", "idempotency_key": key}).json() == first.json()
    assert Directive.objects.count() == before


def test_target_change_refuses_before_enqueue(client, operator, catalog):
    from shopman.shop.models import Channel

    body = observed(client, operator)
    Channel.objects.filter(ref="ifood").update(is_active=False)
    before = Directive.objects.count()
    response = client.post(URL, body, content_type="application/json", HTTP_IDEMPOTENCY_KEY=str(uuid4()))
    assert response.status_code == 409
    assert Directive.objects.count() == before


def test_second_enqueue_failure_keeps_no_partial_enqueue_or_receipt(client, operator, catalog, monkeypatch):
    from shopman.shop.handlers import catalog_projection

    body = observed(client, operator)
    original = catalog_projection.enqueue_project
    calls = []

    def enqueue(sku, listing_ref, **kwargs):
        calls.append(listing_ref)
        if len(calls) == 2:
            raise RuntimeError("second resync enqueue failed")
        return original(sku, listing_ref, **kwargs)

    monkeypatch.setattr(catalog_projection, "enqueue_project", enqueue)
    key = str(uuid4())
    before = Directive.objects.count()
    with pytest.raises(RuntimeError, match="second resync enqueue failed"):
        client.post(URL, body, content_type="application/json", HTTP_IDEMPOTENCY_KEY=key)
    assert Directive.objects.count() == before
    assert not IdempotencyKey.objects.filter(key=key).exists()


def test_new_intention_adopts_live_canonical_tasks(client, operator, catalog):
    body = observed(client, operator)
    first = client.post(URL, body, content_type="application/json", HTTP_IDEMPOTENCY_KEY=str(uuid4()))
    count = Directive.objects.count()
    second = client.post(URL, body, content_type="application/json", HTTP_IDEMPOTENCY_KEY=str(uuid4()))
    assert second.status_code == 200
    assert second.json()["tasks"] == first.json()["tasks"]
    assert Directive.objects.count() == count


def test_one_key_cannot_switch_the_target(client, operator, catalog):
    body, key = observed(client, operator), str(uuid4())
    assert client.post(URL, {**body, "channel_ref": "web"}, content_type="application/json", HTTP_IDEMPOTENCY_KEY=key).status_code == 200
    count = Directive.objects.count()
    conflict = client.post(URL, {**body, "channel_ref": "ifood"}, content_type="application/json", HTTP_IDEMPOTENCY_KEY=key)
    assert conflict.status_code == 409
    assert conflict.json()["code"] == "intention_conflict"
    assert Directive.objects.count() == count
