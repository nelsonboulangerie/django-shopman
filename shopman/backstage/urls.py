"""Backstage URL configuration — operator-facing routes."""

from __future__ import annotations

from django.http import Http404
from django.urls import path

from shopman.backstage.constants import POS_CHANNEL_REF
from shopman.shop.eventstream import events as eventstream_view

app_name = "backstage"


def user_events_view(request):
    """Stream pessoal ``user-<id>`` do usuário autenticado.

    O id sai da sessão, nunca da URL: não existe forma de pedir a caixa de
    outra pessoa. Anônimo leva 404 antes de delegar, para o ``EventSource``
    falhar limpo em vez de reconectar para sempre contra um 200 com
    ``stream-error`` in-band (mesmo motivo do stream de acompanhamento).
    """
    user = getattr(request, "user", None)
    if not (user and user.is_authenticated):
        raise Http404
    return eventstream_view(
        request, **{"format-channels": ["user-{user_id}"], "user_id": str(user.pk)}
    )


def pos_stock_events_view(request):
    """Stream de estoque do canal do PDV (``stock-<canal do PDV>``), só para o balcão.

    O motor de disponibilidade já publica ``stock-update`` nesse canal a cada
    reserva e movimento (``shop/handlers/_sse_emitters.py``); faltava a porta. Ela
    tem a régua da tela que o evento faz reler (``cashman.operate_pos``, a mesma do
    ``POSView``): o canal ``stock-*`` é efêmero e sem gate no channel manager, e
    aberto a qualquer um ele entregaria o ritmo da loja (o que está esgotando,
    quando o lote entra), o vazamento que a trava do menuboard já fecha. Sem a
    permissão, 404 antes de delegar, para o ``EventSource`` falhar limpo e a grade
    seguir no poll (mesmo motivo do stream pessoal acima).
    """
    user = getattr(request, "user", None)
    if not (user and user.is_authenticated and user.has_perm("cashman.operate_pos")):
        raise Http404
    return eventstream_view(request, channels=[f"stock-{POS_CHANNEL_REF}"])


urlpatterns = [
    # Realtime
    path("events/me/", user_events_view, name="user_events"),
    # Antes do ``events/<kind>/``: ``stock`` não é um canal ``backstage-*``.
    path("events/stock/", pos_stock_events_view, name="pos_stock_events"),
    path(
        "events/<slug:kind>/",
        eventstream_view,
        {"format-channels": ["backstage-{kind}-main"]},
        name="events",
    ),
    path(
        "events/<slug:kind>/<slug:scope>/",
        eventstream_view,
        {"format-channels": ["backstage-{kind}-{scope}"]},
        name="events_scoped",
    ),
    # POS/KDS/Pedidos/alertas/Produção migraram para apps Nuxt dedicados
    # (surfaces/*-nuxt) via api/v1/backstage/*; as camadas de view HTMX
    # foram removidas (SURFACE-CONVERGENCE-PLAN WP1 + OPERATOR-APPS-PLAN Fases 2 e 4),
    # e o console Admin/Unfold de produção saiu no WP-ADM-7d (paridade no Produção).
]
