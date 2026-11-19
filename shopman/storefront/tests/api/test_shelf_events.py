"""GET /api/v1/storefront/shelf/events/ — o aviso público de que a vitrine mudou.

O canal cru de estoque diz o SKU de cada reserva e de cada movimento: aberto ao
público, entrega o ritmo da loja (ADR-018 §5.1). A rota da loja entrega só um
``shelf-update`` sem conteúdo, com janela. Estes testes provam o filtro: nada do
canal cru atravessa, nenhuma mudança se perde, a contagem de eventos some, e o
aviso devido sai quando a janela vence, mesmo com o canal calado.
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

#: Janela dos testes: curta para o teste ser rápido, larga para não oscilar.
WINDOW = 0.15


def stock(sku: str, event_id: str = "1") -> str:
    return f'event: stock-update\nid: stock-web:{event_id}\ndata: {{"sku": "{sku}"}}\n\n'


async def _stream(chunks):
    for chunk in chunks:
        yield chunk


def run(chunks, *, min_interval: float = WINDOW) -> list[str]:
    """Roda o filtro sobre um stream que entrega os pedaços e termina."""

    async def collect() -> list[str]:
        return [chunk async for chunk in coarsen(_stream(chunks), min_interval=min_interval)]

    return asyncio.run(collect())


class LiveSource:
    """Um stream que fica aberto: o teste entrega pedaços quando quer."""

    def __init__(self) -> None:
        self.queue: asyncio.Queue = asyncio.Queue()
        self.closed = False

    def push(self, chunk: str) -> None:
        self.queue.put_nowait(chunk)

    async def __aiter__(self):
        try:
            while True:
                yield await self.queue.get()
        finally:
            self.closed = True


def test_route_is_wired_to_the_coarsening_view():
    match = resolve("/api/v1/storefront/shelf/events/")
    assert match.func is storefront_shelf_events_view


def test_the_window_is_a_few_seconds():
    # "Em poucos segundos" é o que a tela promete; a janela é o pior atraso.
    assert 2.0 <= MIN_INTERVAL_SECONDS <= 10.0


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


def test_the_first_event_after_silence_leaves_at_once():
    async def scenario() -> float:
        source = LiveSource()
        stream = coarsen(source, min_interval=WINDOW)
        loop = asyncio.get_running_loop()
        source.push(stock("A"))
        started = loop.time()
        chunk = await anext(stream)
        elapsed = loop.time() - started
        await stream.aclose()
        assert SHELF_EVENT in chunk
        return elapsed

    assert asyncio.run(scenario()) < WINDOW / 2


def test_an_event_inside_the_window_leaves_when_the_window_ends_even_if_the_channel_goes_quiet():
    async def scenario() -> tuple[str, float]:
        source = LiveSource()
        stream = coarsen(source, min_interval=WINDOW)
        loop = asyncio.get_running_loop()
        source.push(stock("A", "1"))
        await anext(stream)
        sent_at = loop.time()
        # Outra mudança logo em seguida, e depois o canal cala: sem keep-alive,
        # sem evento. O aviso devido tem de sair sozinho, no fim da janela.
        source.push(stock("B", "2"))
        chunk = await asyncio.wait_for(anext(stream), timeout=WINDOW * 10)
        waited = loop.time() - sent_at
        await stream.aclose()
        return chunk, waited

    chunk, waited = asyncio.run(scenario())

    assert chunk.count(SHELF_EVENT) == 1
    assert "B" not in chunk.replace(SHELF_EVENT, "")
    # Nem antes da janela (seria contar a segunda venda), nem muito depois dela.
    assert WINDOW * 0.9 <= waited <= WINDOW * 4


def test_the_number_of_sales_does_not_show():
    async def scenario() -> list[str]:
        source = LiveSource()
        stream = coarsen(source, min_interval=WINDOW)
        out = []
        source.push(stock("A", "0"))
        out.append(await anext(stream))
        # Dez vendas dentro da mesma janela.
        for i in range(1, 11):
            source.push(stock("A", str(i)))
        out.append(await asyncio.wait_for(anext(stream), timeout=WINDOW * 10))
        # Depois disso, silêncio: nada mais sai.
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(anext(stream), timeout=WINDOW * 3)
        return out

    out = "".join(asyncio.run(scenario()))

    # Onze eventos, dois avisos: quem ouve não conta vendas.
    assert out.count(SHELF_EVENT) == 2


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


def test_closing_the_notice_closes_the_source_even_while_waiting():
    async def scenario() -> bool:
        source = LiveSource()
        stream = coarsen(source, min_interval=WINDOW)
        source.push(stock("A"))
        await anext(stream)
        # O cliente sai com o filtro esperando o próximo pedaço.
        waiting = asyncio.ensure_future(anext(stream))
        await asyncio.sleep(0.01)
        waiting.cancel()
        with pytest.raises(asyncio.CancelledError):
            await waiting
        await stream.aclose()
        return source.closed

    assert asyncio.run(scenario()) is True
