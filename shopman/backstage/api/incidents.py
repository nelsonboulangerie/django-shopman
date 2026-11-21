"""Backstage API: o resumo dos incidentes por tipo, para a ponte do GitHub.

GET /api/v1/backstage/incidents/ → um grupo por tipo de alerta com atividade na
janela (dono, severidade, abertos, episódios, verde desde). Só leitura, sem a
mensagem do alerta (pode citar cliente).

Quem lê: superusuário logado, ou a credencial da ponte
(``IncidentReaderCredential``, emitida por ``issue_incident_reader_credential`` e
revogável no Admin). Ela não abre nenhuma outra rota.
"""

from __future__ import annotations

from django.utils import timezone
from rest_framework.permissions import BasePermission
from rest_framework.response import Response
from rest_framework.views import APIView


def bearer_reader(request):
    authorization = str(request.META.get("HTTP_AUTHORIZATION") or "")
    scheme, separator, raw_token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not separator or not raw_token.strip():
        return None
    from shopman.backstage.models import IncidentReaderCredential

    return IncidentReaderCredential.verify(raw_token)


class CanReadIncidents(BasePermission):
    def has_permission(self, request, view):
        user = getattr(request, "user", None)
        if user is not None and getattr(user, "is_superuser", False):
            return True
        return bearer_reader(request) is not None


class IncidentsView(APIView):
    permission_classes = [CanReadIncidents]

    def get(self, request):
        from shopman.backstage.incidents.summary import RECURRING_EPISODES, WINDOW_DAYS, summarize

        groups = summarize()
        return Response(
            {
                "schema_version": 1,
                "generated_at": timezone.now().isoformat(),
                "window_days": WINDOW_DAYS,
                "recurring_episodes": RECURRING_EPISODES,
                "groups": [group.to_dict() for group in groups],
            }
        )
