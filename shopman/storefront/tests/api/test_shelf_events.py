"""GET /api/v1/storefront/shelf/events/ — o aviso público de que a vitrine mudou.

O canal cru de estoque diz o SKU de cada reserva e de cada movimento: aberto ao
público, entrega o ritmo da loja (ADR-018 §5.1). A rota da loja entrega só um
``shelf-update`` sem conteúdo, com janela. Estes testes provam o filtro: nada do
canal cru atravessa, nenhuma mudança se perde, e a contagem de eventos some.
"""

from __future__ import annotations

import asyncio

import pytest
from django.urls import resolve

from shopman.storefront.api.shelf_events import (
    MIN_INTERVAL_SECONDS,
    SHELF_EVENT,
    coarsen,
    storefront_shelf_events_view,
)

OPEN = ":" + " " * 2048 + "\n\nevent: stream-open\ndata:\n\n"
KEEP_ALIVE = "event: keep-alive\ndata:\n\n"


def stock(sku: str, event_id: str = "1") -> str:
    return f'event: stock-update\nid: stock-web:{event_id}\ndata: {{"sku": "{sku}"}}\n\n'


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


async def _stream(chunks):
    for chunk in chunks:
        yield chunk


def run(chunks, *, clock=None) -> list[str]:
    async def collect() -> list[str]:
        return [chunk async for chunk in coarsen(_stream(chunks), clock=clock or Clock())]

    return asyncio.run(collect())


def test_route_is_wired_to_the_coarsening_view():
    match = resolve("/api/v1/storefront/shelf/events/")
    assert match.func is storefront_shelf_events_view


@pytest.mark.django_db
def test_anyone_gets_a_live_event_stream(client):
    resp = client.get("/api/v1/storefront/shelf/events/")

    assert resp.status_code == 200
    assert resp["content-type"].startswith("text/event-stream")
    # Nunca iterar o corpo: é um stream aberto e prenderia o teste.
    resp.close()


def test_stock_event_becomes_a_shelf_update_with_no_payload():
    out = "".join(run([OPEN, stock("TABAT")]))

    assert f"event: {SHELF_EVENT}\ndata: {{}}\n\n" in out
    # Nada do canal cru atravessa: nem o SKU, nem o tipo, nem o id de retomada.
    assert "TABAT" not in out
    assert "stock-update" not in out
    assert "stock-web" not in out
    assert "id:" not in out


def test_control_frames_pass_through():
    out = run([OPEN, KEEP_ALIVE])

    assert "event: stream-open" in out[0]
    assert out[0].startswith(":")
    assert out[1] == KEEP_ALIVE


def test_a_burst_in_one_chunk_is_one_notice():
    # Uma venda mexe em reserva, confirmação e baixa: três eventos, um aviso só.
    out = "".join(run([stock("A", "1") + stock("B", "2") + stock("A", "3")]))

    assert out.count(SHELF_EVENT) == 1


def test_events_inside_the_window_are_owed_and_leave_on_the_next_chunk():
    # O relógio é lido uma vez por pedaço que deve aviso: 1º evento, 2º evento
    # (3 s depois, dentro da janela) e o keep-alive seguinte (já fora dela).
    moments = iter([1000.0, 1003.0, 1003.0 + MIN_INTERVAL_SECONDS])

    out = run([stock("A", "1"), stock("B", "2"), KEEP_ALIVE], clock=lambda: next(moments))

    # 1º evento: sai na hora. 2º: fica devendo, e o pedaço some inteiro. O
    # keep-alive seguinte carrega o aviso devido: nenhuma mudança se perde.
    assert len(out) == 2
    assert out[0].count(SHELF_EVENT) == 1
    assert "keep-alive" in out[1]
    assert out[1].count(SHELF_EVENT) == 1


def test_the_number_of_sales_does_not_show():
    # Dez eventos dentro da mesma janela: quem ouve conta um aviso, não dez vendas.
    out = "".join(run([stock("A", str(i)) for i in range(10)]))

    assert out.count(SHELF_EVENT) == 1


def test_a_quiet_stream_emits_nothing():
    out = "".join(run([OPEN, KEEP_ALIVE, KEEP_ALIVE]))

    assert SHELF_EVENT not in out


def test_channel_refusal_does_not_name_the_channel():
    refusal = 'event: stream-error\nid: error\ndata: {"condition": "forbidden", "text": "x", "channels": ["stock-web"]}\n\n'
    out = "".join(run([refusal]))

    assert "event: stream-error" in out
    assert "stock-web" not in out


def test_bytes_are_accepted():
    out = "".join(run([stock("A").encode()]))

    assert out.count(SHELF_EVENT) == 1
    assert '"sku"' not in out


def test_closing_the_notice_closes_the_source():
    closed = []

    async def source():
        try:
            yield stock("A")
            yield stock("B")
        finally:
            closed.append(True)

    async def consume() -> None:
        stream = coarsen(source(), clock=Clock())
        await anext(stream)
        await stream.aclose()

    asyncio.run(consume())

    assert closed == [True]
