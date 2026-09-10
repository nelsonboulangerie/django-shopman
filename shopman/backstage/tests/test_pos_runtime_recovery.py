"""Regras aprovadas: estação, efeito/recibo e duas estações na mesma comanda."""

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.contrib.auth.models import User
from django.urls import reverse
from rest_framework.exceptions import APIException
from rest_framework.response import Response
from shopman.cashman.models import Entry, Terminal
from shopman.orderman.models import IdempotencyKey, Session

from shopman.backstage.api.operations import _cash_idempotent, _open_cash_shift_for_request, _terminal_do_pedido
from shopman.backstage.projections.pos import build_open_tab
from shopman.backstage.services import pos as cash
from shopman.shop.models import Channel, Shop
from shopman.shop.services import pos

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def runtime():
    user = User.objects.create_superuser("runtime-test", password="local-test")
    terminals = [Terminal.objects.create(ref=ref, label=ref) for ref in ("A", "B")]
    shifts = [cash.open_cash_shift(operator=user, terminal_ref=t.ref) for t in terminals]
    return user, shifts


def test_station_wins_and_body_mismatch_blocks(runtime):
    user, shifts = runtime
    request = SimpleNamespace(user=user, data={}, COOKIES={})
    with patch("shopman.backstage.station_trust.station_ref", return_value="B"):
        assert _open_cash_shift_for_request(request).pk == shifts[1].pk
        request.data = {"terminal_ref": "A"}
        with pytest.raises(APIException):
            _terminal_do_pedido(request)
    with patch("shopman.backstage.station_trust.station_ref", return_value=""):
        with pytest.raises(APIException):
            _terminal_do_pedido(request)


def test_cash_crash_rolls_back_effect_and_receipt(runtime):
    user, shifts = runtime
    request = SimpleNamespace(user=user, data={"client_request_id": "crash"}, COOKIES={})

    def execute():
        cash.register_cash_movement(operator=user, terminal_ref="A", movement_type="suprimento", amount_raw="10")
        return Response({"ok": True})

    original = IdempotencyKey.save

    def fail_receipt(self, *args, **kwargs):
        if self.status == "done":
            raise RuntimeError("receipt failure")
        return original(self, *args, **kwargs)

    with patch("shopman.backstage.station_trust.station_ref", return_value="A"):
        with patch.object(IdempotencyKey, "save", fail_receipt), pytest.raises(RuntimeError):
            _cash_idempotent(request, acao="test", executar=execute)
        assert not Entry.objects.filter(kind=Entry.Kind.CASH_IN).exists()
        assert not IdempotencyKey.objects.filter(key="crash").exists()
        assert _cash_idempotent(request, acao="test", executar=execute).status_code == 200
        assert _cash_idempotent(request, acao="test", executar=execute).status_code == 200
    assert Entry.objects.filter(kind=Entry.Kind.CASH_IN).count() == 1


def test_cash_key_required_and_changed_actor_payload_rejected(runtime):
    user, _ = runtime
    request = SimpleNamespace(user=user, data={}, COOKIES={})
    calls = []

    def execute():
        calls.append(True)
        return Response({"ok": True})

    with patch("shopman.backstage.station_trust.station_ref", return_value="A"):
        assert _cash_idempotent(request, acao="test", executar=execute).status_code == 422
        request.data = {"client_request_id": "same", "amount": "10"}
        assert _cash_idempotent(request, acao="test", executar=execute).status_code == 200
        request.data["amount"] = "20"
        assert _cash_idempotent(request, acao="test", executar=execute).status_code == 409
        request.data["amount"] = "10"
        request.user = User.objects.create_user("other")
        assert _cash_idempotent(request, acao="test", executar=execute).status_code == 409
    assert len(calls) == 1


def test_shared_tab_stale_save_rejected_and_read_does_not_reopen(client, runtime):
    user, _ = runtime
    Shop.objects.create(name="Test", brand_name="Test")
    Channel.objects.create(ref="pdv", name="Balcão", is_active=True)
    from shopman.offerman.models import Product

    Product.objects.create(sku="SHARED", name="Pão", base_price_q=1000, is_sellable=True, is_published=True)
    session = pos.open_pos_tab(
        channel_ref="pdv", tab_ref="77", actor="pos:runtime-test", operator_username=user.username
    )
    original = build_open_tab(session)
    client.force_login(user)
    body = {
        "tab_session_key": session.session_key,
        "expected_revision": original["revision"],
        "items": [{"line_id": "L-shared", "sku": "SHARED", "qty": 1, "unit_price_q": 1000}],
        "payment_method": "cash",
    }
    first = client.post(reverse("api-backstage-pos-tab-save"), body, content_type="application/json")
    assert first.status_code == 200, first.content
    assert first.json()["revision"] != original["revision"]
    body["items"][0]["qty"] = 2
    stale = client.post(reverse("api-backstage-pos-tab-save"), body, content_type="application/json")
    assert stale.status_code == 409, stale.content
    session.refresh_from_db()
    assert int(session.items[0]["qty"]) == 1
    current = client.get(reverse("api-backstage-pos-tab-open", args=["77"]))
    assert current.status_code == 200, current.content
    assert current.json()["revision"] == first.json()["revision"]
    Session.objects.filter(pk=session.pk).update(state="committed")
    assert client.get(reverse("api-backstage-pos-tab-open", args=["77"])).status_code == 409
    assert Session.objects.count() == 1


@pytest.mark.parametrize(
    "method,amount", [("pix", 500), ("pix", 1500), ("credit", 500), ("credit", 1500), ("mixed", 1500)]
)
def test_explicit_non_cash_and_mixed_must_equal_total(method, amount):
    from shopman.shop.services.pos_intent import PosIntentError

    tenders = [{"method": "pix" if method == "mixed" else method, "amount_q": amount, "collection": "terminal"}]
    if method == "mixed":
        tenders.append({"method": "cash", "amount_q": 100, "collection": "terminal"})
    with pytest.raises(PosIntentError):
        pos._payload_tenders(
            {"payment_method": method, "payment_tenders": tenders},
            payment_collection="terminal",
            total_q=1000,
            pos_terminal_ref="A",
            require_complete=True,
        )


def test_real_station_cookies_ambiguous_revoked_and_inactive(client, runtime):
    from shopman.backstage.station_trust import station_ref
    from shopman.backstage.tests.pos_test_runtime import bind_station

    user, _ = runtime
    device_a = bind_station(client, "A")
    request = SimpleNamespace(COOKIES={k: v.value for k, v in client.cookies.items()}, META={})
    assert station_ref(request) == "A"
    device_b = bind_station(client, "B")
    request.COOKIES = {k: v.value for k, v in client.cookies.items()}
    assert station_ref(request) == ""
    device_b.revoke()
    assert station_ref(request) == "A"
    Terminal.objects.filter(ref="A").update(is_active=False)
    request.data = {}
    with pytest.raises(APIException):
        _terminal_do_pedido(request)
    device_a.revoke()
    assert station_ref(request) == ""


def test_two_database_connections_same_cash_attempt_commit_once(runtime):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    from django.db import close_old_connections

    from shopman.shop.services.remote_mutations import run_idempotent_mutation

    user, _ = runtime
    barrier = Barrier(2)

    def worker():
        close_old_connections()
        try:
            operator = User.objects.get(pk=user.pk)
            barrier.wait(timeout=10)

            def execute():
                cash.register_cash_movement(
                    operator=operator, terminal_ref="A", movement_type="suprimento", amount_raw="10"
                )
                return {"ok": True}, 200

            return run_idempotent_mutation(
                scope="pos.test.concurrent", key="one", fingerprint="same", atomic_effect=True, execute=execute
            )
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: worker(), range(2)))
    assert sorted(r.replayed for r in results) == [False, True]
    assert Entry.objects.filter(kind=Entry.Kind.CASH_IN).count() == 1


def test_sale_receipt_lookup_checks_actor_station_and_survives_closed_shift(client, runtime):
    from shopman.orderman.models import Order

    from shopman.backstage.tests.pos_test_runtime import bind_station

    user, shifts = runtime
    order = Order.objects.create(ref="ORDER-recovery", channel_ref="pdv", session_key="committed-test", total_q=1000)
    IdempotencyKey.objects.create(
        scope="pos_sale:pdv",
        key="lost-response",
        status="done",
        response_body={"version": 1, "actor": user.username, "terminal_ref": "A", "order_ref": order.ref},
    )
    from shopman.cashman.models import Shift

    Shift.objects.filter(pk=shifts[0].pk).update(status="closed")
    client.force_login(user)
    bind_station(client, "A")
    url = reverse("api-backstage-pos-close-sale")
    response = client.get(url, {"client_request_id": "lost-response"})
    assert response.status_code == 200, response.content
    assert response.json()["order_ref"] == order.ref
    other = User.objects.create_superuser("receipt-other", password="local-test")
    client.force_login(other)
    assert client.get(url, {"client_request_id": "lost-response"}).status_code == 409
    assert Order.objects.count() == 1


def test_line_authorship_is_server_owned_and_noop_save_keeps_original():
    Shop.objects.create(name="Test", brand_name="Test")
    Channel.objects.create(ref="pdv", name="Balcão")
    from shopman.offerman.models import Product

    Product.objects.create(sku="AUTHOR", name="Pão", base_price_q=1000, is_sellable=True, is_published=True)
    session = pos.open_pos_tab(channel_ref="pdv", tab_ref="88", actor="pos:ana", operator_username="ana")
    body = {
        "tab_session_key": session.session_key,
        "items": [
            {
                "line_id": "L-author",
                "sku": "AUTHOR",
                "qty": 1,
                "unit_price_q": 1000,
                "authorship": {"created_by": "forged", "updated_by": "forged"},
            }
        ],
    }

    def save(actor):
        pos.save_pos_tab(channel_ref="pdv", payload=body, actor=f"pos:{actor}", operator_username=actor)
        session.refresh_from_db()
        return build_open_tab(session)["items"][0]["authorship"]

    first = save("ana")
    assert first["created_by"] == first["updated_by"] == "ana"
    assert save("bruno") == first
    body["items"][0]["qty"] = 2
    edited = save("bruno")
    assert edited["created_by"] == "ana"
    assert edited["created_at"] == first["created_at"]
    assert edited["updated_by"] == "bruno"
    assert edited["updated_at"] != first["updated_at"]


def test_two_real_browser_contexts_share_edit_and_close_once(live_server, tmp_path):
    """Django/PostgreSQL reais por HTTP, cookies distintos, Chromium independente."""
    import json
    import os
    import subprocess
    from pathlib import Path

    from django.test import Client
    from shopman.offerman.models import Product
    from shopman.orderman.models import Order

    from shopman.backstage.tests.pos_test_runtime import bind_station

    Shop.objects.create(name="Test", brand_name="Test")
    Channel.objects.create(ref="pdv", name="Balcão", config={"payment": {"method": "cash", "timing": "external"}})
    Product.objects.create(sku="BROWSER", name="Pão", base_price_q=1000, is_sellable=True, is_published=True)
    cookies = []
    shifts = {}
    for actor in ("tablet", "pc"):
        user = User.objects.create_superuser(f"browser-{actor}", password="local-test")
        terminal = Terminal.objects.create(ref=f"browser-{actor}", label=actor)
        shifts[actor] = cash.open_cash_shift(operator=user, terminal_ref=terminal.ref)
        client = Client()
        client.force_login(user)
        bind_station(client, terminal.ref)
        client.cookies["csrftoken"] = "a" * 32
        cookies.append([{"name": k, "value": v.value} for k, v in client.cookies.items()])
    fixture = tmp_path / "browser-fixture.json"
    fixture.write_text(json.dumps({"url": live_server.url, "cookies": cookies}))
    root = Path(__file__).resolve().parents[3]
    env = {**os.environ, "PATH": "/opt/homebrew/opt/node@22/bin:" + os.environ["PATH"]}
    run = subprocess.run(
        ["node", str(root / "surfaces/pos-nuxt/tests/e2e/shared-tab-api.cjs"), str(fixture)],
        cwd=root,
        env=env,
        text=True,
        capture_output=True,
        timeout=60,
    )
    assert run.returncode == 0, run.stdout + run.stderr
    result = json.loads(run.stdout.strip().splitlines()[-1])
    assert Order.objects.count() == 1
    entry = Entry.objects.get(kind=Entry.Kind.SALE)
    assert entry.shift_id == shifts[result["winner"]].pk
    assert entry.amount_q == 2000


def test_total_changed_after_review_rolls_back_sale(runtime):
    from shopman.offerman.models import Product
    from shopman.orderman.models import Order

    user, shifts = runtime
    Shop.objects.create(name="Test", brand_name="Test")
    Channel.objects.create(ref="pdv", name="Balcão", config={"payment": {"method": "cash", "timing": "external"}})
    Product.objects.create(sku="PRICE", name="Pão", base_price_q=1000, is_sellable=True, is_published=True)
    from shopman.shop.services.pos_intent import PosIntentError

    with pytest.raises(PosIntentError, match="total mudou"):
        pos.close_sale(
            channel_ref="pdv",
            actor=f"pos:{user.username}",
            operator_username=user.username,
            payload={
                "client_request_id": "price-changed",
                "items": [{"sku": "PRICE", "qty": 1, "unit_price_q": 1000}],
                "payment_method": "cash",
                "cash_shift_id": shifts[0].pk,
                "pos_terminal_ref": "A",
                "review_total_q": 900,
            },
        )
    assert not Order.objects.exists()
    assert not Entry.objects.filter(kind=Entry.Kind.SALE).exists()
    assert not IdempotencyKey.objects.filter(key="price-changed").exists()


def test_cleanup_never_erases_monetary_attempts():
    from datetime import timedelta
    from io import StringIO

    from django.core.management import call_command
    from django.utils import timezone

    old = timezone.now() - timedelta(days=30)
    for scope in ["pos_sale:pdv", "pos.cash.cash_movement", "unrelated-cache"]:
        idem = IdempotencyKey.objects.create(scope=scope, key="expired", status="done", expires_at=old)
        IdempotencyKey.objects.filter(pk=idem.pk).update(created_at=old)
    call_command("cleanup_idempotency_keys", include_in_progress=True, stdout=StringIO())
    assert set(IdempotencyKey.objects.values_list("scope", flat=True)) == {"pos_sale:pdv", "pos.cash.cash_movement"}
