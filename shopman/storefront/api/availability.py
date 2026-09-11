"""Availability API endpoint — public, no auth, cached."""

from __future__ import annotations

from decimal import Decimal

from django.core.cache import cache
from django.http import Http404
from django.utils.decorators import method_decorator
from django_ratelimit.decorators import ratelimit
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import status
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from shopman.shop.services import availability as avail_service
from shopman.storefront.api.serializers import (
    AvailabilityResponseSerializer,
    StockAlertManagementActionSerializer,
    StockAlertManagementStateSerializer,
    StockAlertSubscribeRequestSerializer,
    StockAlertSubscribeResponseSerializer,
    StockAlertSubscriptionControlRequestSerializer,
    StockAlertSubscriptionControlResponseSerializer,
    StockAlertSubscriptionRefSerializer,
)
from shopman.storefront.services import catalog as catalog_service


@extend_schema_view(
    get=extend_schema(
        tags=["availability"],
        summary="Get product availability",
        parameters=[
            OpenApiParameter("channel", str, description="Optional channel scope."),
        ],
        responses={200: AvailabilityResponseSerializer},
    ),
)
class AvailabilityView(APIView):
    """
    GET /api/v1/availability/<sku>/?channel=<channel_ref>

    Returns the current availability status for a SKU, optionally scoped
    to a channel (listing gate + channel-specific stock scope).

    Response:
        {
            "ok": bool,
            "available_qty": str,   # Decimal as string
            "badge_text": str,      # Human-readable label (pt-BR)
            "badge_class": str,     # CSS class for badge rendering
            "is_bundle": bool,
        }

    Cache TTL: 10 seconds per (sku, channel_ref).
    """

    authentication_classes = []
    permission_classes = []
    serializer_class = AvailabilityResponseSerializer

    def get(self, request, sku):
        if not catalog_service.product_exists(sku):
            raise Http404

        channel_ref = request.GET.get("channel")
        cache_key = f"availability:{sku}:{channel_ref or 'default'}"

        cached = cache.get(cache_key)
        if cached:
            return Response(cached)

        result = avail_service.check(sku, Decimal("1"), channel_ref=channel_ref)

        badge_text, badge_class = _badge_for(result)

        data = {
            "ok": result["ok"],
            "available_qty": str(result["available_qty"]),
            "badge_text": badge_text,
            "badge_class": badge_class,
            "is_bundle": result.get("is_bundle", False),
        }

        cache.set(cache_key, data, 10)
        return Response(data)


@method_decorator(ratelimit(key="user_or_ip", rate="10/m", method="POST", block=False), name="dispatch")
class StockAlertSubscribeView(APIView):
    """POST /api/v1/availability/<sku>/notify/ — "Me avise quando…".

    Aberto a cliente logado (usa o telefone da conta) ou anônimo (telefone no
    corpo). Registra uma assinatura persistente.

    O corpo PODE escolher o gatilho via ``alert_type`` (``stock_back`` ou
    ``production_ready``), mas a loja não escolhe: ela manda só o telefone, e
    quem decide o eixo é o servidor, pela natureza do produto — ver
    ``stock_alerts.default_alert_type``. A tela do cliente diz "avise-me sobre
    este produto"; saber que pão sai do forno e refrigerante volta à prateleira
    é trabalho da casa, não dele.
    """

    authentication_classes = [SessionAuthentication]
    permission_classes = [AllowAny]

    @extend_schema(
        tags=["availability"],
        summary="Subscribe to a persistent product alert",
        request=StockAlertSubscribeRequestSerializer,
        responses={200: StockAlertSubscribeResponseSerializer},
    )
    def post(self, request, sku):
        if getattr(request, "limited", False):
            return Response(
                {"detail": "Muitas tentativas. Aguarde um instante."},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )
        if not catalog_service.product_exists(sku):
            raise Http404

        from shopman.storefront.constants import STOREFRONT_CHANNEL_REF
        from shopman.storefront.identity import get_authenticated_customer
        from shopman.storefront.intents._phone import normalize_phone_input
        from shopman.storefront.models import StockAlertSubscription
        from shopman.storefront.services import stock_alerts

        alert_type = str(request.data.get("alert_type") or "").strip()
        if alert_type and alert_type not in StockAlertSubscription.AlertType.values:
            return Response(
                {"detail": "Tipo de aviso desconhecido.", "field": "alert_type"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        customer = get_authenticated_customer(request)
        phone = normalize_phone_input(str(request.data.get("phone") or "")) or ""
        if customer is None and not phone:
            return Response(
                {"detail": "Informe um telefone para avisarmos quando voltar.", "field": "phone"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        channel_ref = request.GET.get("channel") or STOREFRONT_CHANNEL_REF
        sub = stock_alerts.subscribe(
            sku,
            channel_ref=channel_ref,
            customer=customer,
            phone=phone,
            alert_type=alert_type,
        )
        if sub is None:
            return Response(
                {"detail": "Não foi possível registrar o aviso."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        # Persiste o estado do sino p/ anônimo com contato + SKU. O marcador
        # legado guardava só o SKU e ficava preso depois que o aviso era enviado.
        session = getattr(request, "session", None)
        if session is not None:
            session.pop("stock_alert_skus", None)
            marked = session.get("stock_alert_subscriptions")
            marked = list(marked) if isinstance(marked, (list, tuple)) else []
            marker = {
                "ref": str(sub.ref),
                "sku": sub.sku,
                "alert_type": sub.alert_type,
                "contact_phone": sub.contact_phone,
            }
            if marker not in marked:
                marked.append(marker)
                session["stock_alert_subscriptions"] = marked
        return _no_store_response(
            {
                "ok": True,
                "subscription_ref": str(sub.ref),
                "active": sub.is_active,
                "expires_at": sub.expires_at.isoformat() if sub.expires_at else None,
                "management_url": stock_alerts.management_url(sub),
            },
            status_code=status.HTTP_200_OK,
        )

    @extend_schema(
        tags=["availability"],
        summary="Pause or resume one owned product alert",
        request=StockAlertSubscriptionControlRequestSerializer,
        responses={200: StockAlertSubscriptionControlResponseSerializer},
    )
    def patch(self, request, sku):
        """Pause/resume the exact opt-in without changing its consent evidence."""
        from shopman.storefront.identity import get_authenticated_customer
        from shopman.storefront.services import stock_alerts

        subscription_ref = str(request.data.get("subscription_ref") or "").strip()
        action = str(request.data.get("action") or "").strip()
        if not subscription_ref or action not in {"pause", "resume"}:
            return Response(
                {"detail": "Informe o aviso e a ação pause ou resume."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        customer = get_authenticated_customer(request)
        phone, owned_marker = _anonymous_marker(request, subscription_ref)
        if customer is None and owned_marker is None:
            return Response({"detail": "Aviso não encontrado."}, status=status.HTTP_404_NOT_FOUND)
        changed = stock_alerts.set_paused(
            subscription_ref,
            paused=action == "pause",
            sku=sku,
            customer=customer,
            phone=phone,
        )
        if not changed:
            return Response({"detail": "Aviso não encontrado."}, status=status.HTTP_404_NOT_FOUND)
        return Response({"ok": True, "active": action == "resume"})

    @extend_schema(
        tags=["availability"],
        summary="Cancel one owned product alert",
        request=StockAlertSubscriptionRefSerializer,
        responses={200: StockAlertSubscriptionControlResponseSerializer},
    )
    def delete(self, request, sku):
        """Cancel a subscription without exposing whether another person's ref exists."""

        from shopman.storefront.identity import get_authenticated_customer
        from shopman.storefront.services import stock_alerts

        subscription_ref = str(request.data.get("subscription_ref") or "").strip()
        if not subscription_ref:
            return Response(
                {"detail": "Informe qual aviso deseja cancelar.", "field": "subscription_ref"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        customer = get_authenticated_customer(request)
        phone, owned_marker = _anonymous_marker(request, subscription_ref)
        session = getattr(request, "session", None)
        markers = session.get("stock_alert_subscriptions", []) if session is not None else []
        markers = list(markers) if isinstance(markers, (list, tuple)) else []
        if customer is None:
            if owned_marker is None:
                return Response(
                    {"detail": "Aviso não encontrado."},
                    status=status.HTTP_404_NOT_FOUND,
                )

        cancelled = stock_alerts.revoke(
            subscription_ref,
            sku=sku,
            customer=customer,
            phone=phone,
        )
        if not cancelled:
            return Response(
                {"detail": "Aviso não encontrado ou já concluído."},
                status=status.HTTP_404_NOT_FOUND,
            )
        if session is not None and owned_marker is not None:
            session["stock_alert_subscriptions"] = [item for item in markers if item is not owned_marker]
        return Response({"ok": True, "cancelled": True})


def _anonymous_marker(request, subscription_ref: str) -> tuple[str, dict | None]:
    session = getattr(request, "session", None)
    markers = session.get("stock_alert_subscriptions", []) if session is not None else []
    markers = list(markers) if isinstance(markers, (list, tuple)) else []
    marker = next((item for item in markers if str(item.get("ref") or "") == subscription_ref), None)
    return (str(marker.get("contact_phone") or "") if marker else "", marker)


_MANAGEMENT_CAPABILITY_HEADER = OpenApiParameter(
    "X-Stock-Alert-Capability",
    str,
    location=OpenApiParameter.HEADER,
    required=True,
    description="Opaque capability from the management link fragment.",
)


@extend_schema_view(
    get=extend_schema(
        tags=["availability"],
        summary="Read one product alert state",
        parameters=[_MANAGEMENT_CAPABILITY_HEADER],
        responses={200: StockAlertManagementStateSerializer},
    ),
    patch=extend_schema(
        tags=["availability"],
        summary="Pause or resume one product alert",
        parameters=[_MANAGEMENT_CAPABILITY_HEADER],
        request=StockAlertManagementActionSerializer,
        responses={200: StockAlertManagementStateSerializer},
    ),
    delete=extend_schema(
        tags=["availability"],
        summary="Cancel one product alert",
        parameters=[_MANAGEMENT_CAPABILITY_HEADER],
        request=None,
        responses={200: StockAlertManagementStateSerializer},
    ),
)
class StockAlertManagementView(APIView):
    """Cross-device control for one purpose-scoped stock alert capability."""

    authentication_classes = [SessionAuthentication]
    permission_classes = [AllowAny]

    def get(self, request):
        """Read state only; link scanners cannot change the subscription."""
        from shopman.storefront.services import stock_alerts

        sub = stock_alerts.subscription_for_management(_management_capability(request))
        if sub is None:
            return _management_not_found()
        return _management_response(sub)

    def patch(self, request):
        from shopman.storefront.services import stock_alerts

        action = str(request.data.get("action") or "").strip()
        if action not in {"pause", "resume"}:
            return _management_response_data(
                {"detail": "Escolha pausar ou retomar."},
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        outcome = stock_alerts.set_paused_by_capability(
            _management_capability(request),
            paused=action == "pause",
        )
        if outcome is None:
            return _management_not_found()
        sub, suppressed = outcome
        return _management_response(sub, suppressed=suppressed)

    def delete(self, request):
        from shopman.storefront.services import stock_alerts

        outcome = stock_alerts.revoke_by_capability(_management_capability(request))
        if outcome is None:
            return _management_not_found()
        sub, suppressed = outcome
        return _management_response(sub, suppressed=suppressed)


def _management_capability(request) -> str:
    return str(request.headers.get("X-Stock-Alert-Capability") or "").strip()


def _management_payload(sub, *, suppressed: int = 0) -> dict:
    from shopman.storefront.models import StockAlertDelivery, StockAlertSubscription
    from shopman.storefront.services.stock_alerts import product_name

    accepted = sub.deliveries.filter(status=StockAlertDelivery.Status.ACCEPTED).count()
    unresolved = sub.deliveries.filter(status=StockAlertDelivery.Status.INDETERMINATE).count()
    state = "cancelled" if sub.revoked_at is not None else "paused" if sub.paused_at is not None else "active"
    return {
        "ok": True,
        "product_name": product_name(sub.sku),
        "event_label": dict(StockAlertSubscription.AlertType.choices).get(sub.alert_type, sub.alert_type),
        "state": state,
        "can_pause": state == "active",
        "can_resume": state == "paused",
        "can_cancel": state in {"active", "paused"},
        "suppressed_deliveries": suppressed,
        "accepted_deliveries": accepted,
        "unresolved_deliveries": unresolved,
        "delivery_note": "Mensagens já aceitas pelo provedor não podem ser retiradas.",
    }


def _management_response(sub, *, suppressed: int = 0, status_code: int = status.HTTP_200_OK):
    return _management_response_data(_management_payload(sub, suppressed=suppressed), status_code=status_code)


def _management_not_found():
    return _management_response_data(
        {"detail": "Este link de gestão não é válido."},
        status_code=status.HTTP_404_NOT_FOUND,
    )


def _management_response_data(data: dict, *, status_code: int):
    return _no_store_response(data, status_code=status_code)


def _no_store_response(data: dict, *, status_code: int):
    response = Response(data, status=status_code)
    response["Cache-Control"] = "private, no-store, max-age=0"
    response["Pragma"] = "no-cache"
    response["Referrer-Policy"] = "no-referrer"
    return response


def _badge_for(result: dict) -> tuple[str, str]:
    """Derive Portuguese badge text and CSS class from an availability result.

    Vocabulário canônico (AVAILABILITY-PLAN §2): qualquer estado que não seja
    "pode pedir agora" vira "Indisponível" — um único rótulo.
    """
    if result["ok"]:
        return "Disponível", "badge-available"
    return "Indisponível", "badge-unavailable"
