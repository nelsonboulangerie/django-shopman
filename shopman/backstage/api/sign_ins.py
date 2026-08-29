"""Backstage API — os acessos da PRÓPRIA conta.

GET /api/v1/backstage/sign-ins/ → os últimos acessos de quem está pedindo

⚠️ **Filtrado por ``request.user``, sem exceção e sem parâmetro que mude isso.**
Não é zelo: um balconista que lê "quem entrou quando" da loja inteira sabe quem
estava no balcão em cada hora do mês, e isso seria criar um problema novo ao
resolver o antigo. Quem precisa ver a trilha de TODOS é o gerente, e o caminho
disso é a tela de Auditoria no Admin, atrás de ``backstage.view_signinevent``.

Irmão de ``notifications.py`` na mesma leitura: aquele é a caixa da pessoa, este
é o histórico dela. O aviso aponta para cá — é o que faz "conferir sempre que
quiser" acontecer sem depender de lembrar de um caminho.
"""

from __future__ import annotations

from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema, extend_schema_view
from rest_framework.response import Response
from rest_framework.views import APIView

from shopman.backstage.models import SignInEvent
from shopman.backstage.services.sign_in_audit import ANOMALY_LABELS

from .permissions import IsBackstageOperator

_DEFAULT_LIMIT = 30
_MAX_LIMIT = 100


def _sign_in_dict(event: SignInEvent) -> dict:
    realces = event.anomalies
    return {
        "pk": event.pk,
        "method": event.method,
        "method_display": event.get_method_display(),
        "outcome": event.outcome,
        "outcome_display": event.get_outcome_display(),
        # Vazio quer dizer "de fora da loja" — informação, não lacuna. A tela
        # mostra a frase, não um campo em branco.
        "station_ref": event.station_ref,
        "station_display": event.station_ref or "fora da loja",
        "ip_address": event.ip_address or "",
        "created_at": event.created_at.isoformat(),
        "created_at_display": timezone.localtime(event.created_at).strftime("%d/%m às %H:%M"),
        # O realce viaja como DADO, e não como uma lista separada: a tela mostra
        # uma lista só e o olho para no que é anômalo, sem que nada tenha sido
        # escondido num silo.
        "anomalies": realces,
        "anomaly_labels": [ANOMALY_LABELS.get(code, code) for code in realces],
        "highlight": bool(realces),
    }


@extend_schema_view(
    get=extend_schema(
        tags=["backstage"],
        summary="Sign-in history for the current user (own account only)",
        parameters=[OpenApiParameter("limit", int, description="Máximo de itens (default 30).")],
        responses={200: OpenApiResponse(description="Sign-ins, newest first.")},
    ),
)
class SignInListView(APIView):
    permission_classes = [IsBackstageOperator]

    def get(self, request):
        # `user=request.user` e nada mais. Sem `user_id` de query string, sem
        # ramo para staff privilegiado: a porta que não existe não vaza.
        queryset = SignInEvent.objects.filter(user=request.user)
        eventos = list(queryset[: _limit(request)])
        return Response({
            "sign_ins": [_sign_in_dict(e) for e in eventos],
            "highlighted_count": sum(1 for e in eventos if e.anomalies),
        })


def _limit(request) -> int:
    raw = request.query_params.get("limit")
    try:
        return max(1, min(int(raw), _MAX_LIMIT)) if raw else _DEFAULT_LIMIT
    except (TypeError, ValueError):
        return _DEFAULT_LIMIT
