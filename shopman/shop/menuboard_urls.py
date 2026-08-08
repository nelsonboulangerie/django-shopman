"""URLs dos canais de EXIBIÇÃO — quadro na TV (interno) e feed de plataforma (público).

Um Feed exibe um conjunto de coleções para fora, sem transacionar: menuboard
(quadro numa TV, tempo real via SSE) e feed (RSS 2.0 que Google/Meta buscam agendado).
"""

from __future__ import annotations

from django.urls import path
from django_eventstream.views import events as eventstream_view

from shopman.shop.menuboard_access import menuboard_access_denied
from shopman.shop.views.menuboard import MenuboardDataView, MenuboardPageView
from shopman.shop.views.product_feed import ProductFeedView


def _gated_eventstream(request, ref: str, **kwargs):
    """``eventstream_view`` atrás da trava do menuboard.

    O SSE vem de ``django_eventstream``, então a trava entra por wrapper em vez de
    mixin. ``ref`` só serve para autorizar: o canal assinado é o mesmo para todos os
    quadros (``stock-catalog``).
    """
    denied = menuboard_access_denied(request, ref)
    if denied is not None:
        return denied
    return eventstream_view(request, **kwargs)

urlpatterns = [
    # Feed de produtos (Google Merchant / Meta) — pull; o parceiro agenda o fetch.
    path("feed/<slug:ref>.xml", ProductFeedView.as_view(), name="product-feed"),
    path("menuboard/<slug:ref>/", MenuboardPageView.as_view(), name="menuboard"),
    path("menuboard/<slug:ref>/data/", MenuboardDataView.as_view(), name="menuboard-data"),
    # Stream ``stock-catalog``: o motor de disponibilidade emite nele em toda mudança
    # de estado do produto (ver shop/handlers/_sse_emitters.py). Todos os menuboards
    # assinam o mesmo canal (refletem o estado canônico do catálogo).
    #
    # Passa pela MESMA trava da página: sem ela, qualquer visitante assinaria o fluxo
    # ao vivo do catálogo e leria o ritmo operacional da loja — o que está esgotando,
    # quando a fornada entra. Era o vazamento mais sério das quatro rotas.
    path(
        "menuboard/<slug:ref>/events/",
        _gated_eventstream,
        {"channels": ["stock-catalog"]},
        name="menuboard-events",
    ),
]
