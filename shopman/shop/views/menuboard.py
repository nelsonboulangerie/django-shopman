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
from django.views import View

from shopman.shop.menuboard_access import ensure_display_trust, menuboard_access_denied
from shopman.shop.projections.menuboard import MenuboardError, build_menuboard


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
            {"ref": ref, "initial": json.dumps(asdict(board), ensure_ascii=False)},
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
