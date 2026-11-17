"""Backstage API — a loja no iFood (card do canal iFood e sinal da fila).

GET  /api/v1/backstage/ifood/store/          → projeção (quem vê a fila de pedidos)
GET  /api/v1/backstage/ifood/widget/         → qual widget do iFood carregar (vazio = nenhum)
GET  …/ifood/merchants/, merchant/, interruptions/, opening-hours/ → a loja no iFood ao vivo (abaixo)

Ligar e desligar o iFood (com período) é o toggle "Ativo" do card, comum a todos
os canais: ``POST /api/v1/backstage/feeds/switch/``.
"""

from __future__ import annotations

from dataclasses import asdict

from drf_spectacular.utils import extend_schema, extend_schema_view, inline_serializer
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from shopman.backstage.projections.ifood_store import (
    build_ifood_store_projection,
    build_ifood_widget_projection,
)

from .permissions import HasBackstagePermission

_STORE_RESPONSE = inline_serializer(
    name="IFoodStoreProjectionResponse",
    fields={
        "enabled": serializers.BooleanField(),
        "governs": serializers.BooleanField(),
        "channel_off": serializers.BooleanField(),
        "shop_open": serializers.BooleanField(),
        "shop_message": serializers.CharField(),
        "ifood_available": serializers.BooleanField(allow_null=True),
        "ifood_status_label": serializers.CharField(),
        "ifood_checked_at_display": serializers.CharField(),
        "ifood_problems": serializers.ListField(child=serializers.CharField()),
        "diverges": serializers.BooleanField(),
    },
)


def _projection(request) -> dict:
    return asdict(build_ifood_store_projection(user=request.user))


@extend_schema_view(
    get=extend_schema(
        tags=["backstage"], summary="A loja no iFood (status e conferência)", responses={200: _STORE_RESPONSE}
    ),
)
class IFoodStoreView(APIView):
    permission_classes = [HasBackstagePermission]
    required_permission = "shop.manage_orders"

    def get(self, request):
        return Response(_projection(request))


_WIDGET_RESPONSE = inline_serializer(
    name="IFoodWidgetProjectionResponse",
    fields={
        "widget_id": serializers.CharField(),
        "merchant_ids": serializers.ListField(child=serializers.CharField()),
        "has_order_in_progress": serializers.BooleanField(),
    },
)


@extend_schema_view(
    get=extend_schema(
        tags=["backstage"],
        summary="O widget do iFood (chat com o cliente) a carregar no Gestor",
        responses={200: _WIDGET_RESPONSE},
    ),
)
class IFoodWidgetView(APIView):
    permission_classes = [HasBackstagePermission]
    required_permission = "shop.manage_orders"

    def get(self, request):
        return Response(asdict(build_ifood_widget_projection()))


# ── A loja no iFood, ao vivo (módulo Merchant) ────────────────────────────────
#
# GET    /api/v1/backstage/ifood/merchants/                 → lojas vinculadas ao app
# GET    /api/v1/backstage/ifood/merchant/                  → detalhe + disponibilidade
# GET    /api/v1/backstage/ifood/interruptions/             → pausas no iFood (e as recusadas)
# DELETE /api/v1/backstage/ifood/interruptions/<id>/        → remove pausa feita no Portal
# GET    /api/v1/backstage/ifood/opening-hours/             → horário no iFood × horário da casa
# POST   /api/v1/backstage/ifood/opening-hours/write/       → grava agora o horário da casa no iFood
#
# Integração desligada (sem client_id/merchant_id/chave): ``{"enabled": false}``.


def _live(build):
    from shopman.shop.services import ifood_merchant

    if not ifood_merchant.enabled():
        return Response({"enabled": False})
    return Response({"enabled": True, **asdict(build())})


_LIVE_RESPONSE = inline_serializer(
    name="IFoodMerchantLiveResponse",
    fields={"enabled": serializers.BooleanField()},
)


class _IFoodLiveView(APIView):
    permission_classes = [HasBackstagePermission]
    required_permission = "shop.manage_orders"


@extend_schema_view(
    get=extend_schema(tags=["backstage"], summary="Lojas vinculadas ao app no iFood", responses={200: _LIVE_RESPONSE})
)
class IFoodMerchantsView(_IFoodLiveView):
    def get(self, request):
        from shopman.backstage.projections.ifood_merchant_console import build_merchants

        return _live(build_merchants)


@extend_schema_view(
    get=extend_schema(
        tags=["backstage"], summary="Detalhe e disponibilidade da loja no iFood", responses={200: _LIVE_RESPONSE}
    )
)
class IFoodMerchantView(_IFoodLiveView):
    def get(self, request):
        from shopman.backstage.projections.ifood_merchant_console import build_merchant

        return _live(build_merchant)


@extend_schema_view(
    get=extend_schema(tags=["backstage"], summary="Pausas da loja no iFood", responses={200: _LIVE_RESPONSE})
)
class IFoodInterruptionsView(_IFoodLiveView):
    def get(self, request):
        from shopman.backstage.projections.ifood_merchant_console import build_interruptions

        return _live(build_interruptions)


@extend_schema_view(
    delete=extend_schema(
        tags=["backstage"],
        summary="Remove no iFood uma pausa feita no Portal do Parceiro",
        responses={200: _LIVE_RESPONSE},
    )
)
class IFoodInterruptionDetailView(_IFoodLiveView):
    """Só gerente (a régua do toggle do canal): remover pausa reabre a loja no iFood."""

    required_permission = ("shop.manage_orders", "cashman.adjust_shift")

    def delete(self, request, interruption_id: str):
        from shopman.backstage.projections.ifood_merchant_console import (
            PauseNotRemovable,
            api_error_copy,
            build_interruptions,
            remove_portal_interruption,
        )
        from shopman.shop.services import ifood_merchant

        if not ifood_merchant.enabled():
            return Response({"detail": "A integração com o iFood está desligada."}, status=404)
        try:
            remove_portal_interruption(interruption_id)
        except PauseNotRemovable:
            return Response(
                {"detail": "Esta pausa é do Gestor ou do calendário: para tirá-la, ligue o iFood de novo no canal."},
                status=409,
            )
        except ifood_merchant.MerchantAPIError as exc:
            return Response({"detail": api_error_copy(exc)}, status=502)
        return Response({"enabled": True, **asdict(build_interruptions())})


@extend_schema_view(
    get=extend_schema(
        tags=["backstage"], summary="Horário no iFood comparado ao da casa", responses={200: _LIVE_RESPONSE}
    )
)
class IFoodOpeningHoursView(_IFoodLiveView):
    def get(self, request):
        from shopman.backstage.projections.ifood_merchant_console import build_opening_hours

        return _live(build_opening_hours)


@extend_schema_view(
    post=extend_schema(
        tags=["backstage"], summary="Grava agora o horário da casa no iFood", responses={200: _LIVE_RESPONSE}
    )
)
class IFoodOpeningHoursWriteView(_IFoodLiveView):
    """Só gerente (a régua do toggle do canal): o horário decide quando a loja vende."""

    required_permission = ("shop.manage_orders", "cashman.adjust_shift")

    def post(self, request):
        from shopman.backstage.projections.ifood_merchant_console import api_error_copy, write_opening_hours
        from shopman.shop.services import ifood_merchant

        if not ifood_merchant.enabled():
            return Response({"detail": "A integração com o iFood está desligada."}, status=404)
        try:
            projection = write_opening_hours()
        except ifood_merchant.MerchantAPIError as exc:
            return Response({"detail": api_error_copy(exc)}, status=502)
        return Response({"enabled": True, **asdict(projection)})
