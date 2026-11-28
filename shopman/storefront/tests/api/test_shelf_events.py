"""GET /api/v1/storefront/shelf/events/ — o aviso público de que a vitrine mudou (#2784).

Quem publica é o shop, no canal ``shelf-<canal>``, só quando o estado público de um SKU
muda (``shop/services/public_shelf.py``; os testes dele provam que dez vendas sem
mudança não geram aviso). A rota filtra esse canal: passa o ``shelf-update`` com o SKU
validado e os quadros de controle; nada mais atravessa, nem o ``id`` de retomada.
"""

from __future__ import annotations

import asyncio

import pytest
from django.urls import resolve

from shopman.storefront.api.shelf_events import SHELF_EVENT, public_frames, storefront_shelf_events_view

OPEN = ":" + " " * 2048 + "\n\nevent: stream-open\ndata:\n\n"
KEEP_ALIVE = "event: keep-alive\ndata:\n\n"


def shelf(data: str, event_id: str = "1") -> str:
    return f"event: shelf-update\nid: shelf-web:{event_id}\ndata: {data}\n\n"


async def _stream(chunks):
    for chunk in chunks:
        yield chunk


def run(chunks) -> list[str]:
    async def collect() -> list[str]:
        return [chunk async for chunk in public_frames(_stream(chunks))]

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


def test_route_is_wired_to_the_public_view():
    match = resolve("/api/v1/storefront/shelf/events/")
    assert match.func is storefront_shelf_events_view


@pytest.mark.django_db
def test_anyone_gets_a_live_event_stream(client):
    resp = client.get("/api/v1/storefront/shelf/events/")

    assert resp.status_code == 200
    assert resp["content-type"].startswith("text/event-stream")
    # Nunca iterar o corpo: é um stream aberto e prenderia o teste.
    resp.close()


def test_the_notice_carries_the_sku_and_nothing_else():
    out = "".join(run([OPEN, shelf('{"sku": "TABAT", "extra": "x"}')]))

    assert f'event: {SHELF_EVENT}\ndata: {{"sku": "TABAT"}}\n\n' in out
    # Nem o id de retomada, nem o nome do canal, nem campo a mais.
    assert "id:" not in out
    assert "shelf-web" not in out
    assert "extra" not in out


def test_a_notice_without_sku_means_the_whole_shelf():
    out = "".join(run([shelf("{}")]))

    assert f"event: {SHELF_EVENT}\ndata: {{}}\n\n" in out


def test_an_odd_sku_does_not_cross():
    out = "".join(run([shelf('{"sku": "<script>"}'), shelf("not json", "2")]))

    assert "<script>" not in out
    assert "not json" not in out
    assert out.count(f"event: {SHELF_EVENT}\ndata: {{}}") == 2


def test_other_events_of_the_channel_do_not_cross():
    out = "".join(run([OPEN, 'event: stock-update\ndata: {"sku": "A"}\n\n']))

    assert "stock-update" not in out
    assert SHELF_EVENT not in out


def test_control_frames_pass_through():
    out = run([OPEN, KEEP_ALIVE])

    assert "event: stream-open" in out[0]
    assert out[0].startswith(":")
    assert out[1] == KEEP_ALIVE


def test_channel_refusal_does_not_name_the_channel():
    refusal = 'event: stream-error\nid: error\ndata: {"condition": "forbidden", "text": "x", "channels": ["shelf-web"]}\n\n'
    out = "".join(run([refusal]))

    assert "event: stream-error" in out
    assert "shelf-web" not in out


def test_bytes_are_accepted():
    out = "".join(run([shelf('{"sku": "A"}').encode()]))

    assert out.count(SHELF_EVENT) == 1


def test_closing_the_notice_closes_the_source_even_while_waiting():
    async def scenario() -> bool:
        source = LiveSource()
        stream = public_frames(source)
        source.push(shelf('{"sku": "A"}'))
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
