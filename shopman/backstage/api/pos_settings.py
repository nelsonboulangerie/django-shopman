"""Backstage API: PDV › Ajustes (Impressoras, Maquininhas, Envio à cozinha, Atalhos de venda).

GET  /api/v1/backstage/pos/settings/  → o que cada aba lê
POST /api/v1/backstage/pos/settings/  → uma mudança por vez, ``{"section": ..., ...}``

Seções do POST:

- ``printer``: ``{terminal_ref, roll_width_mm, cut_mode}``
- ``card_machine``: ``{ref?, label, identification?, active}`` (sem ``ref`` = nova)
- ``kitchen_station``: ``{station_ref, auto_fire}``
- ``shortcuts``: ``{terminal_ref, favorite_collection_refs: [...]}``

A régua é a do balcão (``cashman.operate_pos``), como o Salão (decisão do dono,
04/10/2026: quem opera o PDV ajusta o PDV). Erro no dialeto da casa.
"""

from __future__ import annotations

from rest_framework.response import Response
from rest_framework.views import APIView

from shopman.backstage.services import pos_settings

from .permissions import HasBackstagePermission


def _terminal(request):
    from shopman.cashman.models import Terminal

    from shopman.backstage import station_trust

    ref = station_trust.station_ref(request)
    return Terminal.objects.filter(ref=ref, is_active=True).first() if ref else None


def _error(exc: pos_settings.PosSettingsError) -> Response:
    field = exc.field or None
    body = {"detail": str(exc), "field": field, "error": {"code": exc.code}}
    if field:
        body["errors"] = {field: [str(exc)]}
    return Response(body, status=400)


class POSSettingsView(APIView):
    permission_classes = [HasBackstagePermission]
    required_permission = "cashman.operate_pos"

    def get(self, request):
        return Response(pos_settings.build_settings(terminal=_terminal(request)))

    def post(self, request):
        body = request.data if isinstance(request.data, dict) else {}
        actor = request.user.get_username() if request.user and request.user.is_authenticated else ""
        section = body.get("section")
        try:
            if section == "printer":
                pos_settings.update_printer(
                    terminal_ref=str(body.get("terminal_ref") or ""),
                    roll_width_mm=body.get("roll_width_mm"),
                    cut_mode=str(body.get("cut_mode") or ""),
                    actor=actor,
                )
            elif section == "card_machine":
                pos_settings.save_card_machine(
                    ref=str(body.get("ref") or ""),
                    label=str(body.get("label") or ""),
                    identification=str(body.get("identification") or ""),
                    active=bool(body.get("active", True)),
                    actor=actor,
                )
            elif section == "kitchen_station":
                pos_settings.set_station_auto_fire(
                    station_ref=str(body.get("station_ref") or ""),
                    enabled=bool(body.get("auto_fire")),
                    actor=actor,
                )
            elif section == "shortcuts":
                pos_settings.set_favorite_collections(
                    terminal_ref=str(body.get("terminal_ref") or ""),
                    refs=body.get("favorite_collection_refs"),
                    actor=actor,
                )
            else:
                raise pos_settings.PosSettingsError("Escolha o que ajustar.", field="section")
        except pos_settings.PosSettingsError as exc:
            return _error(exc)
        return Response(pos_settings.build_settings(terminal=_terminal(request)))
