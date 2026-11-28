"""O "Separado" da Preparação: a porta HTTP da marca que vale para a bancada inteira.

``GET ?date=`` devolve as marcas que valem agora para o dia (as de quantidade velha
já caíram). ``POST`` marca ou desmarca um item:
``{"date", "item_ref", "quantity", "checked"}``. A resposta traz a marca que vale
(``mark``, ``null`` quando o item ficou desmarcado) e a lista do dia inteira
(``marks``), para que a tela que gravou não precise de uma segunda leitura.

* ``item_ref``: ``<sku>`` numa linha da lista de separação, ``<recipe_ref>/<sku>``
  no ingrediente de um preparo (``services.prep_checklist``).
* ``quantity``: a quantidade que a pessoa separou, exatamente como a tela mostrou.
  Se ela não é mais a do item, a resposta é 409 com a quantidade de agora.

Permissão: a mesma de abrir a Preparação (``can_view_prep``); quem marca é o
operador do PIN (a sessão). A estação autônoma (o Letreiro, sem ninguém para digitar
PIN) só lê: escrever dela é 403.

A rota mora sob ``/api/v1/backstage/production/``, ao lado da Preparação, e a marca
tem leitura e escrita próprias: não entra na projeção da Preparação.
"""

from __future__ import annotations

from django.utils import timezone
from drf_spectacular.utils import OpenApiResponse, extend_schema, extend_schema_view
from rest_framework import serializers
from rest_framework.exceptions import APIException, PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from shopman.backstage import station_trust
from shopman.backstage.services import prep_checklist

from ._production_filters import ProductionDateQuerySerializer, validated_query
from .permissions import HasProductionCapability


class PrepChecklistMarkSerializer(serializers.Serializer):
    """O gesto de quem separou: o item, a quantidade que viu e se separou."""

    date = serializers.DateField()
    item_ref = serializers.CharField(max_length=prep_checklist.MAX_ITEM_REF_LENGTH, trim_whitespace=True)
    quantity = serializers.CharField(
        max_length=prep_checklist.MAX_QUANTITY_LENGTH,
        trim_whitespace=True,
        allow_blank=True,
        required=False,
        default="",
    )
    checked = serializers.BooleanField()

    def validate_item_ref(self, value: str) -> str:
        try:
            return prep_checklist.normalize_item_ref(value)
        except prep_checklist.PrepChecklistError as exc:
            raise serializers.ValidationError(str(exc)) from exc

    def validate(self, attrs):
        if attrs["checked"] and not attrs.get("quantity"):
            raise serializers.ValidationError({"quantity": ["Diga a quantidade que foi separada."]})
        return attrs


class PrepChecklistQuantityChangedError(APIException):
    status_code = 409
    default_code = "prep_quantity_changed"
    default_detail = "A quantidade mudou. Confira e separe de novo."


def _marks_payload(selected_date, access) -> list[dict]:
    return [mark.as_dict() for mark in prep_checklist.marks_for(selected_date=selected_date, access=access)]


@extend_schema_view(
    get=extend_schema(
        tags=["backstage"],
        summary="Prep checklist marks valid now for the day (shared by every tablet)",
        responses={200: OpenApiResponse(description="Marks whose quantity is still the current one.")},
    ),
    post=extend_schema(
        tags=["backstage"],
        summary="Mark or unmark one prep item as separated",
        responses={
            200: OpenApiResponse(description="The mark that holds now, and the day's marks."),
            403: OpenApiResponse(description="Autonomous station: the signage only reads."),
            409: OpenApiResponse(description="The item's quantity changed since the operator looked."),
        },
    ),
)
class ProductionPrepChecklistView(APIView):
    permission_classes = [HasProductionCapability]
    required_production_capability = "can_view_prep"

    def get(self, request):
        query = validated_query(request, ProductionDateQuerySerializer)
        selected_date = query.get("date") or timezone.localdate()
        access = request.production_access
        return Response(
            {
                "date": selected_date.isoformat(),
                "marks": _marks_payload(selected_date, access),
            }
        )

    def post(self, request):
        if station_trust.station_mode(request) == station_trust.AUTONOMOUS:
            raise PermissionDenied(
                "A estação autônoma só lê o Separado: quem marca é quem separa, com o PIN.",
                code="autonomous_station_read_only",
            )
        serializer = PrepChecklistMarkSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        access = request.production_access
        try:
            mark = prep_checklist.set_mark(
                selected_date=data["date"],
                item_ref=data["item_ref"],
                quantity=data.get("quantity", ""),
                checked=data["checked"],
                user=request.user,
                access=access,
            )
        except prep_checklist.PrepChecklistQuantityChanged as exc:
            raise PrepChecklistQuantityChangedError(
                {
                    "detail": str(exc),
                    "field": "quantity",
                    "item_ref": exc.item_ref,
                    "current_quantities": list(exc.current),
                }
            ) from exc
        except prep_checklist.PrepChecklistError as exc:
            raise serializers.ValidationError({"item_ref": [str(exc)]}) from exc
        return Response(
            {
                "date": data["date"].isoformat(),
                "mark": mark.as_dict() if mark else None,
                "marks": _marks_payload(data["date"], access),
            }
        )
