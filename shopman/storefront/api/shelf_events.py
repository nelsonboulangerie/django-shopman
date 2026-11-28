"""O aviso público de que a vitrine mudou (WP-L04, "loja viva"; #2784).

A loja precisa saber, sem recarregar, que a disponibilidade mudou: o produto que
esgotou, a fornada que ficou pronta. Quem publica é o shop, no canal
``shelf-<canal da loja>`` (``shop/services/public_shelf.py``), e só quando muda o que
QUALQUER visitante já vê daquele SKU (o estado do card, as últimas unidades, o dia da
promessa). Dez vendas que não mudam nada disso não geram aviso.

O canal cru de estoque (``stock-<canal>``) **não** vem ao público: cada evento dele é
uma venda ou uma entrada de lote, e aberto entregaria o ritmo da loja (ADR-018 §5.1).
Até o #2784 esta rota embrulhava esse canal cru num aviso sem conteúdo, no máximo um a
cada 5 s, e toda página aberta relia a cada aviso, mesmo quando a mudança não a
afetava. Agora o aviso leva o SKU, e a página relê só quando o SKU é dela.

Mesmo vindo de um canal já público, a rota passa só o que precisa:

- ``shelf-update`` com ``{"sku": "<SKU>"}`` (SKU validado) ou ``{}`` (a vitrine
  inteira, quando a lista do canal muda);
- os quadros de controle do próprio stream (``stream-open``, ``keep-alive``) e a
  recusa, sem o corpo original (que nomeia o canal);
- nada mais: nem ``id`` de retomada, nem outro tipo de evento.
"""

from __future__ import annotations

import contextlib
import json
import re

from shopman.shop.eventstream import events as eventstream_view
from shopman.shop.services import public_shelf
from shopman.storefront.constants import STOREFRONT_CHANNEL_REF

#: O único evento de conteúdo que a rota pública emite.
SHELF_EVENT = public_shelf.SHELF_EVENT

#: Quadros de controle do ``django_eventstream`` que seguem como vieram.
_CONTROL_EVENTS = frozenset({"stream-open", "keep-alive"})

#: Recusa do canal: segue como erro de stream, sem o corpo original (que nomeia o canal).
_ERROR_FRAME = 'event: stream-error\ndata: {"condition": "forbidden"}'

#: O formato de SKU que pode sair (letras, dígitos, hífen e sublinhado).
_SKU = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")


def _frame_field(frame: str, field: str) -> str:
    """O valor de um campo do quadro SSE (``event``, ``data``); vazio se não houver."""
    prefix = f"{field}:"
    for line in frame.split("\n"):
        if line.startswith(prefix):
            return line.removeprefix(prefix).strip()
    return ""


def _shelf_frame(frame: str) -> str:
    """O ``shelf-update`` reescrito só com o SKU validado; ``{}`` quando não há SKU."""
    try:
        data = json.loads(_frame_field(frame, "data") or "{}")
    except ValueError:
        data = {}
    sku = data.get("sku") if isinstance(data, dict) else None
    body = {"sku": sku} if isinstance(sku, str) and _SKU.match(sku) else {}
    return f"event: {SHELF_EVENT}\ndata: {json.dumps(body)}"


async def public_frames(content):
    """Filtra o stream do canal público: passa o aviso com o SKU e o controle, e só."""
    try:
        async for chunk in content:
            text = chunk.decode("utf-8", "replace") if isinstance(chunk, bytes | bytearray) else str(chunk)
            out: list[str] = []
            for frame in text.split("\n\n"):
                if not frame.strip():
                    continue
                if frame.startswith(":"):
                    # Comentário (o enchimento que abre o stream): mantém os proxies fluindo.
                    out.append(frame)
                    continue
                event_type = _frame_field(frame, "event")
                if event_type in _CONTROL_EVENTS:
                    out.append(frame)
                elif event_type == "stream-error":
                    out.append(_ERROR_FRAME)
                elif event_type == SHELF_EVENT:
                    out.append(_shelf_frame(frame))
            if out:
                yield "\n\n".join(out) + "\n\n"
    finally:
        # O cliente saiu: o stream de baixo fecha junto, e o ``finally`` dele roda
        # (o cuidado de ``shopman.shop.eventstream._release_between_reads``).
        aclose = getattr(content, "aclose", None)
        if aclose is not None:
            with contextlib.suppress(Exception):
                await aclose()


def storefront_shelf_events_view(request):
    """Stream público da loja: ``shelf-update`` com o SKU cujo estado público mudou.

    Sem login e sem dado que a vitrine já não mostre. O teto de streams por sessão e
    a vida máxima do stream são os de toda rota SSE (``shopman.shop.eventstream.events``).
    """
    response = eventstream_view(request, channels=[public_shelf.shelf_channel(STOREFRONT_CHANNEL_REF)])
    if getattr(response, "streaming", False) and getattr(response, "is_async", False):
        response.streaming_content = public_frames(response.streaming_content)
    return response
