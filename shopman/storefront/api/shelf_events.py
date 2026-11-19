"""O aviso público de que a vitrine mudou (WP-L04, "loja viva").

A loja precisa saber, sem recarregar, que a disponibilidade mudou: o produto que
esgotou, a fornada que ficou pronta. O motor de disponibilidade já publica isso no
canal ``stock-<canal da loja>`` (``shop/handlers/_sse_emitters.py``), a cada reserva
e a cada movimento de estoque.

Esse canal cru **não** pode ir ao público. Cada evento dele é uma venda ou uma
entrada de lote, com o SKU: aberto a qualquer um, entrega o ritmo da loja (o que
está vendendo, quanto e quando a fornada entra). É o vazamento que a ADR-018 §5.1
fechou no menuboard e que o PDV fechou em ``pos_stock_events_view``.

O que a cliente pode saber é o que a vitrine já mostra a qualquer visitante. Por
isso esta rota entrega só um aviso **sem conteúdo**: ``shelf-update``, sem SKU, sem
motivo, no máximo um a cada :data:`MIN_INTERVAL_SECONDS` por conexão. Quem ouve
refaz a leitura canônica da página em que está (ADR-016); o aviso não diz o que
mudou nem quantas vezes.

- Borda de subida: o primeiro evento depois de um silêncio sai na hora (a cliente
  vê o item mudar em segundos).
- Borda de descida: evento que cai dentro da janela fica devendo e sai no próximo
  pedaço do stream (outro evento, ou o keep-alive de 20 s). Nenhuma mudança se perde.
- Tudo o mais do canal (payload, tipo do evento, ``id`` de retomada) é descartado.
  Passam só os quadros de controle do próprio stream.
"""

from __future__ import annotations

import asyncio
import contextlib

from shopman.shop.eventstream import events as eventstream_view
from shopman.storefront.constants import STOREFRONT_CHANNEL_REF

#: O único evento que a rota pública emite.
SHELF_EVENT = "shelf-update"

#: Janela mínima entre dois avisos na mesma conexão.
MIN_INTERVAL_SECONDS = 10.0

#: Quadros de controle do ``django_eventstream`` que seguem como vieram.
_CONTROL_EVENTS = frozenset({"stream-open", "keep-alive"})

_SHELF_FRAME = f"event: {SHELF_EVENT}\ndata: {{}}"
#: Recusa do canal: segue como erro de stream, sem o corpo original (que nomeia o canal).
_ERROR_FRAME = 'event: stream-error\ndata: {"condition": "forbidden"}'


def _frame_event(frame: str) -> str:
    """O tipo do quadro SSE; vazio para comentário (linha que começa com ``:``)."""
    for line in frame.split("\n"):
        if line.startswith("event:"):
            return line.removeprefix("event:").strip()
    return ""


async def coarsen(content, *, min_interval: float = MIN_INTERVAL_SECONDS, clock=None):
    """Troca os eventos do canal de estoque por um aviso sem conteúdo, com janela.

    ``content`` é o corpo do stream (pedaços de texto ou bytes, cada um com um ou
    mais quadros SSE). ``clock`` é injetável para o teste; em produção é o relógio
    monotônico do loop.
    """
    now = clock or asyncio.get_running_loop().time
    last_sent: float | None = None
    owed = False
    async with contextlib.aclosing(content) as source:
        async for chunk in source:
            text = chunk.decode("utf-8", "replace") if isinstance(chunk, bytes | bytearray) else str(chunk)
            out: list[str] = []
            for frame in text.split("\n\n"):
                if not frame.strip():
                    continue
                if frame.startswith(":"):
                    # Comentário (o enchimento que abre o stream): mantém os proxies fluindo.
                    out.append(frame)
                    continue
                event_type = _frame_event(frame)
                if event_type in _CONTROL_EVENTS:
                    out.append(frame)
                elif event_type == "stream-error":
                    out.append(_ERROR_FRAME)
                elif event_type == "stream-reset":
                    continue
                else:
                    owed = True
            if owed:
                moment = now()
                if last_sent is None or moment - last_sent >= min_interval:
                    out.append(_SHELF_FRAME)
                    last_sent = moment
                    owed = False
            if out:
                yield "\n\n".join(out) + "\n\n"


def storefront_shelf_events_view(request):
    """Stream público da loja: ``shelf-update`` quando a vitrine pode ter mudado.

    Sem login e sem dado: o que a rota entrega é só o instante em que vale reler a
    página. O teto de streams por sessão e a vida máxima do stream são os de toda
    rota SSE (``shopman.shop.eventstream.events``).
    """
    response = eventstream_view(request, channels=[f"stock-{STOREFRONT_CHANNEL_REF}"])
    if getattr(response, "streaming", False) and getattr(response, "is_async", False):
        response.streaming_content = coarsen(response.streaming_content)
    return response
