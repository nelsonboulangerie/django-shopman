from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from django.db import connection, connections
from django.test import Client
from django.urls import reverse
from shopman.orderman.models import Order

from shopman.backstage.projections.pos import build_open_tab
from shopman.shop.services import pos
from shopman.shop.tests.test_pos_cash_ledger import _Counter

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def tab(client):
    counter = _Counter()
    counter.operator.is_staff = counter.operator.is_superuser = True
    counter.operator.save()
    client.force_login(counter.operator)
    session = pos.open_pos_tab(channel_ref="pdv", tab_ref="77", actor="test", operator_username=counter.operator.username)
    body = {"tab_session_key": session.session_key, "expected_revision": build_open_tab(session)["revision"],
            "items": [{"line_id": "L-test", "sku": "PAO", "qty": 1, "unit_price_q": 1200}], "payment_method": "cash"}
    return counter, session, body


def test_stale_save_does_not_overwrite_other_device(client, tab):
    _, session, body = tab
    first = client.post(reverse("api-backstage-pos-tab-save"), body, content_type="application/json")
    assert first.status_code == 200, first.content
    assert first.json()["revision"] != body["expected_revision"]
    body["items"][0]["qty"] = 2
    stale = client.post(reverse("api-backstage-pos-tab-save"), body, content_type="application/json")
    assert stale.status_code == 409
    session.refresh_from_db()
    assert int(session.items[0]["qty"]) == 1
    current = client.get(reverse("api-backstage-pos-tab-open", args=["77"]))
    assert current.json()["revision"] == first.json()["revision"]


@pytest.mark.skipif(connection.vendor != "postgresql", reason="Requires PostgreSQL row locks across connections")
def test_two_connections_cannot_save_same_revision(tab):
    counter, session, body = tab
    clients = [Client(), Client()]
    for client in clients:
        client.force_login(counter.operator)
    barrier = Barrier(2)
    def worker(client):
        try:
            barrier.wait(timeout=5)
            return client.post(reverse("api-backstage-pos-tab-save"), body, content_type="application/json").status_code
        finally:
            connections.close_all()
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(worker, clients)) == [200, 409]


def test_stale_close_cannot_replace_newer_tab_contents(client, tab):
    _, _, body = tab
    assert client.post(reverse("api-backstage-pos-tab-save"), body, content_type="application/json").status_code == 200
    response = client.post(reverse("api-backstage-pos-close-sale"), {**body, "client_request_id": "stale-close"}, content_type="application/json")
    assert response.status_code == 409, response.content
    assert not Order.objects.exists()


def test_missing_revision_refuses_save_and_close(client, tab):
    _, _, body = tab
    body.pop("expected_revision")
    for name in ["api-backstage-pos-tab-save", "api-backstage-pos-close-sale"]:
        assert client.post(reverse(name), body, content_type="application/json").status_code == 422
    assert not Order.objects.exists()
