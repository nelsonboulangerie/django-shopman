"""Etiquetas de timer — a porta HTTP da fileira de disparo do fournil.

``GET`` devolve as etiquetas ativas, na ordem em que a tela as desenha; ``POST``
cria a que o operador nomeou na hora, **deduplicando por nome comparável**: se
já existe equivalente ativa, ela volta em vez de nascer uma irmã, e a resposta
diz qual dos dois aconteceu (``created``). A tela trata os dois casos igual —
dispara o timer e mostra o chip —, mas a diferença é o que permite avisar
"essa já existia" sem inventar um erro para algo que deu certo.

Permissão: a mesma que governa o app de Produção inteiro
(``can_access_board``). Criar etiqueta é usar o timer, não configurar a casa —
quem pode abrir o quadro pode nomear um lembrete. Curar (renomear, ajustar o
tempo, desativar, apagar) continua sendo do gestor, no Admin.

A rota mora sob ``/api/v1/backstage/production/`` de propósito: é ali que a
estação autônoma (o painel do fournil, sem ninguém para digitar PIN) tem a
conta resolvida — ver ``station_trust.is_production_surface``.

Erros no dialeto canônico ``{detail, field, errors}``, pelo ``EXCEPTION_HANDLER``
da casa (``shopman/shop/api_errors.py``): campo inválido sai 400 com ``field``.
"""

from __future__ import annotations

from drf_spectacular.utils import OpenApiResponse, extend_schema, extend_schema_view
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from shopman.backstage.models import TimerTag
from shopman.backstage.models.timer_tag import MAX_TIMER_MINUTES, normalize_tag_label

from .permissions import HasProductionCapability


class TimerTagCreateSerializer(serializers.Serializer):
    """O que o operador digitou no "Novo timer" antes de pedir para guardar."""

    label = serializers.CharField(max_length=40, trim_whitespace=True)
    minutes = serializers.IntegerField(min_value=1, max_value=MAX_TIMER_MINUTES)

    def validate_label(self, value: str) -> str:
        # Um nome que normaliza para vazio ("---", "   ") viraria um chip mudo,
        # e o gêmeo comparável colidiria com o próximo nome igualmente vazio.
        if not normalize_tag_label(value):
            raise serializers.ValidationError(
                "Dê um nome à etiqueta: só espaço ou pontuação não identifica nada na tela."
            )
        return value.strip()


def timer_tag_projection(tag: TimerTag) -> dict:
    """O que a tela precisa do chip — e nada além disso."""
    return {
        "ref": tag.ref,
        "label": tag.label,
        "minutes": tag.minutes,
        "origin": tag.origin,
    }


@extend_schema_view(
    get=extend_schema(
        tags=["backstage"],
        summary="Timer tags (one-tap presets for the fournil timers page)",
        responses={200: OpenApiResponse(description="Active timer tags, in display order.")},
    ),
    post=extend_schema(
        tags=["backstage"],
        summary="Create a timer tag from the shop floor (deduplicated by name)",
        responses={
            200: OpenApiResponse(description="An equivalent active tag already existed."),
            201: OpenApiResponse(description="Tag created."),
        },
    ),
)
class ProductionTimerTagsView(APIView):
    permission_classes = [HasProductionCapability]
    required_production_capability = "can_access_board"

    def get(self, request):
        tags = TimerTag.objects.active()
        return Response({"tags": [timer_tag_projection(tag) for tag in tags]})

    def post(self, request):
        serializer = TimerTagCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        tag, created = TimerTag.objects.create_from_operator(
            label=serializer.validated_data["label"],
            minutes=serializer.validated_data["minutes"],
        )
        return Response(
            {"tag": timer_tag_projection(tag), "created": created},
            status=201 if created else 200,
        )
