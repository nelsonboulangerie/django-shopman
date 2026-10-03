"""Backstage API — o cadastro de POSTOS de trabalho, para o Gestor › Postos.

GET    /api/v1/backstage/workstations/                          → postos, tipos e copy
POST   /api/v1/backstage/workstations/                          → cria posto sem caixa
PATCH  /api/v1/backstage/workstations/<ref>/                    → renomeia, muda o tipo, liga/desliga
DELETE /api/v1/backstage/workstations/<ref>/devices/<id>/       → solta um dispositivo

A mesma permissão de fixar um dispositivo num posto (``cashman.manage_operators``):
quem decide que um tablet passa a pedir PIN decide também quais postos existem e quem
está neles. O Admin continua podendo; o operador não precisa dele.

O posto Caixa não nasce aqui: ele nasce com o caixa (``Terminal``), que é config de
gaveta e hardware. Aqui ele pode ser renomeado e desligado como qualquer outro posto.
"""

from __future__ import annotations

from rest_framework.response import Response
from rest_framework.views import APIView

from shopman.backstage import station_trust
from shopman.backstage.services import workstations
from shopman.backstage.workstation_vocabulary import COPY, KIND_LABELS

from .permissions import HasBackstagePermission


def _error(exc: workstations.WorkstationError, status: int = 400) -> Response:
    field = exc.field or None
    body = {"detail": str(exc), "field": field, "error": {"code": exc.code}}
    if field:
        body["errors"] = {field: [str(exc)]}
    return Response(body, status=status)


def _state() -> dict:
    return {
        "workstations": workstations.management_list(),
        "kinds": [{"kind": kind, "label": label} for kind, label in KIND_LABELS.items()],
        "copy": dict(COPY),
    }


class WorkstationListView(APIView):
    permission_classes = [HasBackstagePermission]
    required_permission = station_trust.PROVISION_PERM

    def get(self, request):
        return Response({**_state(), "station": station_trust.station_ref(request)})

    def post(self, request):
        body = request.data if isinstance(request.data, dict) else {}
        try:
            workstation = workstations.create(label=body.get("label"), kind=body.get("kind"))
        except workstations.WorkstationError as exc:
            return _error(exc)
        return Response({"workstation": workstations.card(workstation), **_state()}, status=201)


class WorkstationDetailView(APIView):
    permission_classes = [HasBackstagePermission]
    required_permission = station_trust.PROVISION_PERM

    def patch(self, request, ref: str):
        body = request.data if isinstance(request.data, dict) else {}
        is_active = body.get("is_active")
        if is_active is not None and not isinstance(is_active, bool):
            return _error(workstations.WorkstationError("Diga se o posto fica ativo.", field="is_active"))
        try:
            workstations.update(ref, label=body.get("label"), kind=body.get("kind"), is_active=is_active)
        except workstations.WorkstationError as exc:
            return _error(exc, status=404 if exc.code == "workstation_unknown" else 400)
        return Response(_state())


class WorkstationDeviceView(APIView):
    permission_classes = [HasBackstagePermission]
    required_permission = station_trust.PROVISION_PERM

    def delete(self, request, ref: str, device_id: str):
        if not workstations.release_device(ref, device_id):
            return Response({"detail": "Dispositivo não encontrado neste posto."}, status=404)
        return Response(_state())
