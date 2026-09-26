"""
Menuboard views — a superfície DISPLAY pública (quadro-negro numa TV).

Kiosk display (categoria standalone, como KDS/POS): página servida pelo Django que
renderiza o cardápio de uma coleção e atualiza em tempo real via SSE (o mesmo
``stock-{ref}`` que o motor de disponibilidade já emite ao pausar/reprecificar).

Superfície **interna**: exige sessão de staff ou dispositivo confiável — ver
``shopman.shop.menuboard_access`` para o porquê e para o provisionamento da TV. O
feed XML, esse sim público, continua sem exigir nada.
"""

from __future__ import annotations

import json
from dataclasses import asdict

from django.http import Http404, JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views import View

from shopman.shop.menuboard_access import (
    ensure_display_trust,
    menuboard_access_denied,
    menuboard_control_access_denied,
)
from shopman.shop.projections.menuboard import MenuboardError, build_menuboard, resolve_menuboard


class MenuboardPageView(View):
    """Página do quadro-negro (HTML). Embute o estado inicial p/ paint imediato."""

    def get(self, request, ref: str):
        denied = menuboard_access_denied(request, ref)
        if denied is not None:
            return denied
        try:
            board = build_menuboard(ref)
        except MenuboardError as exc:
            raise Http404(str(exc)) from exc
        response = render(
            request,
            "menuboard/board.html",
            {
                "ref": ref,
                # `board` é a pintura do SERVIDOR (a TV desenha sem JS); `initial`
                # é o mesmo estado embutido para o Alpine continuar de onde o
                # servidor parou, sem uma ida à rede só para repetir o que já veio.
                "board": board,
                "initial": json.dumps(asdict(board), ensure_ascii=False),
            },
        )
        # Operador logado abrindo o quadro autoriza ESTE dispositivo: é o
        # provisionamento inteiro da TV, sem token em URL.
        return ensure_display_trust(request, response, ref)


class MenuboardDataView(View):
    """Estado do quadro em JSON (consumido no load + a cada evento SSE)."""

    def get(self, request, ref: str):
        denied = menuboard_access_denied(request, ref)
        if denied is not None:
            return denied
        try:
            board = build_menuboard(ref)
        except MenuboardError as exc:
            return JsonResponse({"detail": str(exc)}, status=404)
        return ensure_display_trust(request, JsonResponse(asdict(board)), ref)


class MenuboardControlView(View):
    """Intenção mínima para o controlador HDMI-CEC do Raspberry Pi.

    Deliberadamente não devolve a projeção do quadro: nenhuma frase, produto ou
    preço. O Chromium autorizado continua sendo o único consumidor do conteúdo.
    """

    def get(self, request, ref: str):
        denied = menuboard_control_access_denied(request, ref)
        if denied is not None:
            return denied
        try:
            channel = resolve_menuboard(ref)
        except MenuboardError as exc:
            return JsonResponse({"detail": str(exc)}, status=404)

        from shopman.shop.services.channel_switch import effective_active
        from shopman.shop.services.menuboard_schedule import resolve_menuboard_automatic_state

        now = timezone.now()
        active = effective_active(channel, now=now)
        automatic = resolve_menuboard_automatic_state(channel, now=now)
        if not active:
            mode = "message"
        elif automatic.is_sleeping:
            mode = "sleep"
        else:
            mode = "content"
        next_transition = automatic.wakes_at if automatic.is_sleeping else automatic.sleeps_at
        return JsonResponse(
            {
                "ref": channel.ref,
                "mode": mode,
                "automatic_enabled": automatic.enabled,
                "standby_allowed": bool(active and automatic.enabled and automatic.is_sleeping),
                "server_time": now.isoformat(),
                "next_transition_at": next_transition.isoformat() if next_transition else None,
            }
        )
