"""C04/C05: interleavings reais com row locks, duas conexões e conservação."""
# ruff: noqa: F401, F811
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Event
from time import monotonic
from types import SimpleNamespace

import pytest
from django.db import close_old_connections, connection, connections, transaction
from shopman.orderman.models import IdempotencyKey, Order, Session
from shopman.stockman.models import Hold

from shopman.shop.models import Conversation
from shopman.shop.services import availability, cart, checkout, sessions
from shopman.storefront.concierge import tools
from shopman.storefront.tests.test_concierge_authority import accept_review
from shopman.storefront.tests.test_concierge_engine import (
    CONCIERGE_SETTINGS,
    SKU,
    _pickup_ready,
    conversation,
    ctx,
    customer,
    surface,
)

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture(autouse=True)
def isolated_callbacks(monkeypatch):
    assert connection.vendor == "postgresql", "Este ensaio exige PostgreSQL real"
    monkeypatch.setattr("shopman.shop.services.payment.initiate", lambda order: None)


class Worker:
    def __init__(self, command):
        self.command = command
        self.started = Event()
        self.pid = None

    def __call__(self):
        close_old_connections()
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_backend_pid()")
                self.pid = cursor.fetchone()[0]
                cursor.execute("SET lock_timeout = '15s'")
            self.started.set()
            try:
                return self.command()
            except Exception as exc:
                return {"exception": type(exc).__name__, "code": getattr(exc, "code", "")}
        finally:
            connections.close_all()


def assert_database_wait(worker):
    assert worker.started.wait(10)
    deadline = monotonic() + 10
    while monotonic() < deadline:
        with connection.cursor() as cursor:
            cursor.execute("SELECT cardinality(pg_blocking_pids(%s))", [worker.pid])
            if cursor.fetchone()[0] > 0:
                return
        Event().wait(0.01)
    pytest.fail(f"Conexão {worker.pid} não entrou em espera real de row lock")


def own_reserved(session_key):
    return availability.own_holds_by_sku(session_key, [SKU]).get(SKU, Decimal(0))


def total_reserved():
    return sum(Hold.objects.active().filter(sku=SKU).values_list("quantity", flat=True), Decimal(0))


def test_modify_waits_for_checkout_commit_and_cannot_change_sealed_order(ctx, monkeypatch):
    quote = _pickup_ready(ctx)
    key = ctx.conversation.session_key
    line_id = Session.objects.get(session_key=key).items[0]["line_id"]
    boundary, release = Event(), Event()
    original = checkout._ensure_total_matches

    def paused_total(*args, **kwargs):
        original(*args, **kwargs)
        boundary.set()  # process_ops possui o lock da Session e validou o total.
        assert release.wait(10)

    monkeypatch.setattr(checkout, "_ensure_total_matches", paused_total)
    commit = Worker(lambda: checkout.process_ops(session_key=key, channel_ref="whatsapp", ops=[],
        idempotency_key="commercial-race-checkout", expected_total_q=quote["total_q"]))
    modify = Worker(lambda: sessions.modify_session(session_key=key, channel_ref="whatsapp",
        ops=[{"op": "set_qty", "line_id": line_id, "qty": 3}]))
    with ThreadPoolExecutor(max_workers=2) as pool:
        committed = pool.submit(commit)
        try:
            assert boundary.wait(10)
            modified = pool.submit(modify)
            assert_database_wait(modify)
        finally:
            release.set()
        result, refusal = committed.result(20), modified.result(20)
    assert hasattr(result, "order_ref"), result
    assert refusal["code"] == "already_committed", refusal
    order = Order.objects.get()
    assert order.ref == result.order_ref and order.total_q == 180
    assert order.items.get(sku=SKU).qty == Decimal(2)
    assert Session.objects.get(session_key=key).state == "committed"
    assert IdempotencyKey.objects.filter(scope__startswith="commit:", status="done").count() == 1
    assert total_reserved() == Decimal(2)


def test_confirmation_waits_for_cart_edit_and_records_conflict_without_order(ctx):
    quote = _pickup_ready(ctx)
    accept_review(ctx, quote)
    key, pk = ctx.conversation.session_key, ctx.conversation.pk
    line_id = Session.objects.get(session_key=key).items[0]["line_id"]
    boundary, release = Event(), Event()

    def edit():
        with transaction.atomic():
            Session.objects.select_for_update().get(session_key=key)
            result = cart.update_qty(session_key=key, channel_ref="whatsapp", line_id=line_id, sku=SKU, qty=3)
            boundary.set()  # Quantidade 3 e holds 3 ainda não visíveis à confirmação.
            assert release.wait(10)
        return result.rev

    edit_worker = Worker(edit)
    confirm = Worker(lambda: tools.place_order(tools.ToolContext(Conversation.objects.get(pk=pk), "whatsapp"), quote["quote_token"], "pix"))
    with ThreadPoolExecutor(max_workers=2) as pool:
        edited = pool.submit(edit_worker)
        try:
            assert boundary.wait(10)
            confirmed = pool.submit(confirm)
            assert_database_wait(confirm)
        finally:
            release.set()
        edited_revision, refusal = edited.result(20), confirmed.result(20)
    assert isinstance(edited_revision, int), edited_revision
    assert refusal["code"] == "revision_conflict", refusal
    assert not Order.objects.exists()
    session = Session.objects.get(session_key=key)
    assert session.state == "open" and Decimal(session.items[0]["qty"]) == Decimal(3)
    assert own_reserved(key) == total_reserved() == Decimal(3)
    receipt = IdempotencyKey.objects.get(scope__startswith="concierge.purchase:")
    assert receipt.status == "done" and receipt.response_body["result"]["code"] == "revision_conflict"
    replay = tools.place_order(ctx, quote["quote_token"], "pix")
    assert replay["code"] == "revision_conflict" and not Order.objects.exists()


@pytest.mark.parametrize("operation", ["update", "add", "remove"])
def test_transfer_and_site_edit_do_not_leave_reservations_on_abandoned_source(ctx, settings, monkeypatch, operation):
    settings.SHOPMAN_CONCIERGE = {**CONCIERGE_SETTINGS, "transfer_enabled": True}
    _pickup_ready(ctx)
    key, pk = ctx.conversation.session_key, ctx.conversation.pk
    line_id = Session.objects.get(session_key=key).items[0]["line_id"]
    boundary, release = Event(), Event()

    def paused_mint(*args, **kwargs):
        boundary.set()  # Origem/holds transferidos, ainda na transação de transferência.
        assert release.wait(10)
        return SimpleNamespace(success=True, url="https://example.invalid/transfer", expires_at="")

    monkeypatch.setattr("shopman.doorman.services.access_link.AccessLinkService.create_token", paused_mint)
    transfer = Worker(lambda: tools.send_web_link(tools.ToolContext(Conversation.objects.get(pk=pk), "whatsapp"), "checkout"))
    commands = {
        "update": lambda: cart.update_qty(session_key=key, channel_ref="whatsapp", line_id=line_id, sku=SKU, qty=3),
        "add": lambda: cart.add_item(session_key=key, channel_ref="whatsapp", origin_channel="web", sku=SKU, qty=1, unit_price_q=90),
        "remove": lambda: cart.remove_item(session_key=key, channel_ref="whatsapp", line_id=line_id, sku=SKU),
    }
    modify = Worker(commands[operation])
    with ThreadPoolExecutor(max_workers=2) as pool:
        transferred = pool.submit(transfer)
        try:
            assert boundary.wait(10)
            modified = pool.submit(modify)
            assert_database_wait(modify)
        finally:
            release.set()
        result, refusal = transferred.result(20), modified.result(20)
    assert result["ok"], result
    assert refusal["code"] == "already_abandoned", refusal
    source = Session.objects.get(session_key=key)
    target = Session.objects.get(session_key=result["resource_ref"])
    assert source.state == "abandoned" and target.state == "open"
    assert target.data["delivery_time_slot"] == "slot-12"
    assert Decimal(target.items[0]["qty"]) == Decimal(2)
    assert own_reserved(key) == 0
    assert own_reserved(target.session_key) == total_reserved() == Decimal(2)
    assert not Order.objects.exists()
    assert IdempotencyKey.objects.filter(scope__startswith="concierge.transfer:", status="done").count() == 1


@pytest.mark.parametrize("operation", ["update", "add", "remove"])
def test_cart_writer_rolls_back_hold_effect_if_session_write_fails(ctx, monkeypatch, operation):
    _pickup_ready(ctx)
    key = ctx.conversation.session_key
    session = Session.objects.get(session_key=key)
    original_items = session.items
    line_id = session.items[0]["line_id"]
    original_holds = list(Hold.objects.active().filter(sku=SKU).values_list("pk", "quantity"))

    def fail_write(**kwargs):
        raise RuntimeError("injected local write failure after stock reconciliation")

    monkeypatch.setattr(sessions, "modify_session", fail_write)
    commands = {
        "update": lambda: cart.update_qty(session_key=key, channel_ref="whatsapp", line_id=line_id, sku=SKU, qty=3),
        "add": lambda: cart.add_item(session_key=key, channel_ref="whatsapp", origin_channel="web", sku=SKU, qty=1, unit_price_q=90),
        "remove": lambda: cart.remove_item(session_key=key, channel_ref="whatsapp", line_id=line_id, sku=SKU),
    }
    with pytest.raises(RuntimeError, match="injected local write failure"):
        commands[operation]()
    session.refresh_from_db()
    assert session.items == original_items and session.state == "open"
    assert own_reserved(key) == total_reserved() == Decimal(2)
    assert list(Hold.objects.active().filter(sku=SKU).values_list("pk", "quantity")) == original_holds
    assert not Order.objects.exists()
