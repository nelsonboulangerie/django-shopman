"""Backstage API — o checklist vivo de cada canal (aba Canais do Gestor).

GET /api/v1/backstage/channels/health/ → um checklist por canal que a casa sabe
conferir (iFood, TV, feed Google/Meta, loja online). Só leitura; cada item traz o
caminho de quem resolve. Gate: ``shop.manage_catalog``, o mesmo da aba Canais.
"""

from __future__ import annotations

from rest_framework.response import Response
from rest_framework.views import APIView

from shopman.backstage.api.permissions import HasBackstagePermission
from shopman.backstage.api.projections import projection_data, read_data
from shopman.backstage.api.telemetry import OperationalObservationMixin


class ChannelHealthView(OperationalObservationMixin, APIView):
    permission_classes = [HasBackstagePermission]
    required_permission = "shop.manage_catalog"

    def get(self, request):
        from shopman.backstage.projections.channel_health import build_channel_health

        return Response(read_data(health=projection_data(build_channel_health())))
