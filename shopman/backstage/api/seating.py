"""Backstage API: o salão desenhado, para o PDV › Ajustes › Salão.

GET  /api/v1/backstage/pos/seating/  → a planta de hoje, o total do B.I. e o histórico
POST /api/v1/backstage/pos/seating/  → grava a planta (um salvar só)

Quem opera o PDV pode redesenhar o salão (decisão do dono, 04/10/2026), então a
régua é a do balcão (``cashman.operate_pos``). Toda gravação fica registrada no
``LogEntry`` com quem, quando e o antes/depois (``services/seating.py``).

Corpo do POST::

    {"revision": "<a que a tela leu>",
     "spots": [{"ref": "mesa-interna-1", "plan_x": 120, "plan_y": 80},
               {"label": "Mesa 9", "shape": "round", "seats": 2, "area": "Calçada"}],
     "removed": ["bistro-2"]}

Erro no dialeto da casa: ``{detail, field, errors}``; conflito de revisão é 409.
"""

from __future__ import annotations

import logging

from rest_framework.response import Response
from rest_framework.views import APIView

from shopman.backstage.projections.seating import build_seating
from shopman.backstage.services import seating as seating_service

from .permissions import HasBackstagePermission

logger = logging.getLogger(__name__)

SEATING_PERMISSION = "cashman.operate_pos"


def _error(exc: seating_service.SeatingError, status: int) -> Response:
    field = exc.field or None
    body = {"detail": str(exc), "field": field, "error": {"code": exc.code}}
    if field:
        body["errors"] = {field: [str(exc)]}
    return Response(body, status=status)


class POSSeatingView(APIView):
    permission_classes = [HasBackstagePermission]
    required_permission = SEATING_PERMISSION

    def get(self, request):
        return Response(build_seating())

    def post(self, request):
        body = request.data if isinstance(request.data, dict) else {}
        expected = body.get("revision")
        if not isinstance(expected, str) or not expected:
            return _error(seating_service.SeatingError("Recarregue o salão antes de salvar.", field="revision"), 400)
        try:
            result = seating_service.save_layout(
                actor=request.user,
                spots=body.get("spots", []),
                removed=body.get("removed", []),
                expected_revision=expected,
            )
        except seating_service.SeatingConflict as exc:
            return _error(exc, 409)
        except seating_service.SeatingError as exc:
            return _error(exc, 400)
        logger.info(
            "pos_seating_saved user=%s changed=%s created=%s versioned=%s removed=%s",
            request.user.pk, result.changed, result.created, result.versioned, result.removed,
        )
        return Response({
            "saved": {
                "changed": result.changed,
                "created": result.created,
                "versioned": result.versioned,
                "removed": result.removed,
            },
            **build_seating(),
        })
