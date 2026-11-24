"""A transferência de sacola contra a edição na origem, com trava de linha real (OC-15, §9.3).

Duas conexões ao PostgreSQL, sem simulação: quem trava a sessão de origem primeiro
decide. Se a edição vence, o aceite espera, lê a revisão nova e recusa com
``source_changed`` (X5): o convite velho não leva a sacola que mudou. Se o aceite
vence, a edição espera e encontra a sacola já levada (``already_abandoned``). Em
nenhuma ordem sobram duas sacolas vivas ou reserva em dobro. O caminho inverso, a
partir da conversa com a Nice, está em
``storefront/tests/test_concierge_commercial_races.py``.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Event
from time import monotonic

import pytest
from django.db import close_old_connections, connection, connections, transaction
from shopman.orderman.models import Session
from shopman.stockman.models import Hold

from shopman.shop.services import cart
from shopman.shop.services import session_transfer as transfer
from shopman.shop.services.session_transfer import TransferDestination, TransferReceipt
from shopman.shop.tests.test_session_transfer import BREAD, CAKE, CHAT, WEB, _chat_cart, _held, ana, store  # noqa: F401

requires_postgres = pytest.mark.skipif(
    connection.vendor != "postgresql",
    reason="Requires independent PostgreSQL connections and row locks",
)

pytestmark = [pytest.mark.django_db(transaction=True), requires_postgres]


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


def _assert_waiting(worker: Worker) -> None:
    assert worker.started.wait(10)
    deadline = monotonic() + 10
    while monotonic() < deadline:
        with connection.cursor() as cursor:
            cursor.execute("SELECT cardinality(pg_blocking_pids(%s))", [worker.pid])
            if cursor.fetchone()[0] > 0:
                return
        Event().wait(0.01)
    pytest.fail(f"Conexão {worker.pid} não entrou em espera real de row lock")


def _all_held() -> Decimal:
    return sum(Hold.objects.active().filter(sku__in=[BREAD, CAKE]).values_list("quantity", flat=True), Decimal(0))


def test_x5_edit_that_holds_the_source_first_makes_the_old_offer_source_changed(store, ana):  # noqa: F811
    source = _chat_cart(ana, (BREAD, 2))
    offer = transfer.offer(CHAT, source.session_key, WEB, customer_ref=ana.ref, actor="concierge")
    editing, release = Event(), Event()

    def edit():
        with transaction.atomic():
            Session.objects.select_for_update().get(pk=source.pk)
            cart.add_item(session_key=source.session_key, channel_ref=CHAT, origin_channel="whatsapp", sku=CAKE,
                          qty=1, unit_price_q=500, name="Bolo")
            editing.set()
            assert release.wait(10)
        return "edited"

    editor = Worker(edit)
    acceptor = Worker(lambda: transfer.accept(offer, dest_context=TransferDestination(customer_ref=ana.ref),
                                              actor="storefront"))
    with ThreadPoolExecutor(max_workers=2) as pool:
        edited = pool.submit(editor)
        try:
            assert editing.wait(10)
            accepted = pool.submit(acceptor)
            _assert_waiting(acceptor)
        finally:
            release.set()
        assert edited.result(20) == "edited"
        refusal = accepted.result(20)

    assert refusal == {"exception": "TransferRefused", "code": "source_changed"}
    source.refresh_from_db()
    assert source.state == "open" and len(source.items) == 2 and "transfer_receipt" not in source.data
    assert not Session.objects.filter(channel_ref=WEB).exists()
    assert _held(source.session_key) == _all_held() == Decimal(3)


def test_accept_that_holds_the_source_first_wins_and_the_late_edit_finds_it_gone(store, ana, monkeypatch):  # noqa: F811
    source = _chat_cart(ana, (BREAD, 2))
    offer = transfer.offer(CHAT, source.session_key, WEB, customer_ref=ana.ref, actor="concierge")
    boundary, release = Event(), Event()
    original_add = cart.add_item

    def paused_add(**kwargs):
        if kwargs.get("channel_ref") == WEB and not boundary.is_set():
            boundary.set()  # origem travada e abandonada, reservas devolvidas, ainda na transação
            assert release.wait(10)
        return original_add(**kwargs)

    monkeypatch.setattr(cart, "add_item", paused_add)
    acceptor = Worker(lambda: transfer.accept(offer, dest_context=TransferDestination(customer_ref=ana.ref),
                                              actor="storefront"))
    editor = Worker(lambda: original_add(session_key=source.session_key, channel_ref=CHAT, origin_channel="whatsapp",
                                         sku=CAKE, qty=1, unit_price_q=500, name="Bolo"))
    with ThreadPoolExecutor(max_workers=2) as pool:
        accepted = pool.submit(acceptor)
        try:
            assert boundary.wait(10)
            edited = pool.submit(editor)
            _assert_waiting(editor)
        finally:
            release.set()
        receipt, refusal = accepted.result(20), edited.result(20)

    assert isinstance(receipt, TransferReceipt), receipt
    assert refusal["code"] == "already_abandoned", refusal
    source.refresh_from_db()
    target = Session.objects.get(session_key=receipt.dest_session_key)
    assert source.state == "abandoned" and target.state == "open"
    assert [line["sku"] for line in target.items] == [BREAD]
    assert _held(source.session_key) == 0
    assert _held(target.session_key) == _all_held() == Decimal(2)


def test_merge_waits_for_an_edit_in_the_destination_and_loses_nothing(store, ana):  # noqa: F811
    """A sacola que recebe os itens está sendo editada: a mescla espera a trava e soma por cima."""
    source = _chat_cart(ana, (BREAD, 2))
    _, browser_key = cart.add_item(session_key=None, channel_ref=WEB, origin_channel="web", sku=BREAD, qty=1,
                                   unit_price_q=100, name="Pão")
    browser = Session.objects.get(session_key=browser_key)
    offer = transfer.offer(CHAT, source.session_key, WEB, customer_ref=ana.ref, actor="concierge")
    editing, release = Event(), Event()

    def edit():
        with transaction.atomic():
            Session.objects.select_for_update().get(pk=browser.pk)
            cart.add_item(session_key=browser_key, channel_ref=WEB, origin_channel="web", sku=CAKE, qty=1,
                          unit_price_q=500, name="Bolo")
            editing.set()
            assert release.wait(10)
        return "edited"

    editor = Worker(edit)
    acceptor = Worker(lambda: transfer.accept(
        offer, dest_context=TransferDestination(customer_ref=ana.ref, session_key=browser_key), actor="storefront",
    ))
    with ThreadPoolExecutor(max_workers=2) as pool:
        edited = pool.submit(editor)
        try:
            assert editing.wait(10)
            accepted = pool.submit(acceptor)
            _assert_waiting(acceptor)
        finally:
            release.set()
        assert edited.result(20) == "edited"
        receipt = accepted.result(20)

    assert isinstance(receipt, TransferReceipt), receipt
    assert receipt.dest_session_key == browser_key and receipt.merged
    target = Session.objects.get(session_key=browser_key)
    assert sorted((line["sku"], Decimal(str(line["qty"]))) for line in target.items) == sorted([
        (BREAD, Decimal(3)), (CAKE, Decimal(1)),
    ])
    assert _held(source.session_key) == 0
    assert _held(browser_key) == _all_held() == Decimal(4)
