"""Backstage Order History API — o Histórico do Gestor.

GET /api/v1/backstage/orders/history/
    ?date_from=YYYY-MM-DD&date_to=YYYY-MM-DD   período do fechamento (padrão: hoje)
    &status=completed,cancelled                 recortes: listas separadas por vírgula
    &channel=web,ifood
    &payment=pix,card,none                      ``none`` = pagamento não informado
    &fulfillment=pickup,delivery
    &q=texto                                    ref, ref externa, nome ou telefone
    &page=N

Gate: ``shop.manage_orders``, a mesma permissão do quadro e do detalhe. Filtro
desconhecido, data malformada ou intervalo invertido é recusado com o dialeto
``{detail, field, errors}``: uma lista que ignora o filtro em silêncio responde
outra pergunta com cara de resposta certa.
"""

from __future__ import annotations

from django.utils import timezone
from drf_spectacular.utils import OpenApiResponse, extend_schema, extend_schema_view
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from shopman.backstage.api._production_filters import StrictQuerySerializer
from shopman.backstage.api.permissions import HasBackstagePermission
from shopman.backstage.api.projections import projection_data, read_data
from shopman.backstage.api.telemetry import OperationalObservationMixin
from shopman.backstage.projections.order_history import (
    FULFILLMENT_LABELS,
    HISTORY_STATUSES,
    HistoryFilters,
    build_order_history,
)

#: Janela máxima de uma consulta: um ano e um dia (o "1A" do seletor de período).
MAX_RANGE_DAYS = 366


class _CommaListField(serializers.CharField):
    """``a,b,c`` → ``("a", "b", "c")``, sem vazios nem repetidos, na ordem dada."""

    def __init__(self, *, choices: tuple[str, ...] | None = None, **kwargs):
        self.allowed = choices
        kwargs.setdefault("required", False)
        kwargs.setdefault("allow_blank", True)
        super().__init__(**kwargs)

    def to_internal_value(self, data):
        raw = super().to_internal_value(data)
        values = tuple(dict.fromkeys(part.strip() for part in raw.split(",") if part.strip()))
        if self.allowed is not None:
            unknown = [value for value in values if value not in self.allowed]
            if unknown:
                raise serializers.ValidationError(f"Valor desconhecido: {', '.join(unknown)}.")
        return values


class OrderHistoryQuerySerializer(StrictQuerySerializer):
    date_from = serializers.DateField(required=False)
    date_to = serializers.DateField(required=False)
    status = _CommaListField(choices=HISTORY_STATUSES)
    channel = _CommaListField(max_length=1000)
    payment = _CommaListField(max_length=1000)
    fulfillment = _CommaListField(choices=tuple(FULFILLMENT_LABELS))
    q = serializers.CharField(required=False, allow_blank=True, max_length=120)
    page = serializers.IntegerField(required=False, min_value=1, default=1)

    def validate(self, attrs):
        today = timezone.localdate()
        date_from = attrs.get("date_from") or attrs.get("date_to") or today
        date_to = attrs.get("date_to") or max(date_from, today)
        if date_to < date_from:
            raise serializers.ValidationError({"date_to": ["O fim do período vem antes do começo."]})
        if (date_to - date_from).days >= MAX_RANGE_DAYS:
            raise serializers.ValidationError({"date_from": ["Escolha um período de até um ano."]})
        attrs["date_from"], attrs["date_to"] = date_from, date_to
        return attrs


@extend_schema_view(
    get=extend_schema(
        tags=["backstage"],
        summary="Order history (closed orders, server-side filters, paginated)",
        responses={
            200: OpenApiResponse(description="Página de pedidos fechados, com as opções de cada recorte."),
            400: OpenApiResponse(description="Filtro desconhecido ou período inválido."),
        },
    ),
)
class OrderHistoryView(OperationalObservationMixin, APIView):
    permission_classes = [HasBackstagePermission]
    required_permission = "shop.manage_orders"

    def get(self, request):
        query = OrderHistoryQuerySerializer(data=request.query_params.dict())
        query.is_valid(raise_exception=True)
        data = query.validated_data
        history = build_order_history(
            HistoryFilters(
                date_from=data["date_from"],
                date_to=data["date_to"],
                statuses=data.get("status") or (),
                channels=data.get("channel") or (),
                payments=data.get("payment") or (),
                fulfillments=data.get("fulfillment") or (),
                query=(data.get("q") or "").strip(),
                page=data["page"],
            )
        )
        return Response(read_data(history=projection_data(history)))
