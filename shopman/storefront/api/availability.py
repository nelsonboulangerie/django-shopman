"""Availability API endpoint — public, no auth, cached."""

from __future__ import annotations

import secrets
import time
import uuid
from datetime import timedelta
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
    StockAlertAuthRequiredResponseSerializer,
    StockAlertIntentRequestSerializer,
    StockAlertIntentResponseSerializer,
    StockAlertManagementActionSerializer,
    StockAlertManagementStateSerializer,
    StockAlertSessionStateSerializer,
    StockAlertSubscribeRequestSerializer,
    StockAlertSubscribeResponseSerializer,
    StockAlertSubscriptionControlRequestSerializer,
    StockAlertSubscriptionControlResponseSerializer,
    StockAlertSubscriptionRefSerializer,
)
from shopman.storefront.services import catalog as catalog_service

_STOCK_ALERT_INTENTS_SESSION_KEY = "stock_alert_intents"
_STOCK_ALERT_INTENT_TTL_SECONDS = 15 * 60
_STOCK_ALERT_INTENT_LIMIT = 5
_STOCK_ALERT_DISCLOSURE_VERSION = "recurring-whatsapp-adult-v1"


def _active_stock_alert_intents(session) -> list[dict]:
    """Return valid short-lived consent proofs from this browser session."""
    now = time.time()
    raw = session.get(_STOCK_ALERT_INTENTS_SESSION_KEY, []) if session is not None else []
    raw = list(raw) if isinstance(raw, (list, tuple)) else []
    active = []
    for marker in raw:
        if not isinstance(marker, dict):
            continue
        try:
            created_at = float(marker.get("created_at") or 0)
        except (TypeError, ValueError):
            continue
        if (
            str(marker.get("ref") or "")
            and str(marker.get("sku") or "")
            and marker.get("adult_declared") is True
            and str(marker.get("disclosure_version") or "") == _STOCK_ALERT_DISCLOSURE_VERSION
            and 0 <= now - created_at <= _STOCK_ALERT_INTENT_TTL_SECONDS
        ):
            active.append(dict(marker))
    if session is not None and active != raw:
        session[_STOCK_ALERT_INTENTS_SESSION_KEY] = active
    return active


def _stock_alert_intent(request, *, sku: str, intent_ref: str, customer_ref: str = "") -> dict | None:
    """Resolve a consent proof owned by this session and, once used, customer."""
    session = getattr(request, "session", None)
    for marker in _active_stock_alert_intents(session):
        if not secrets.compare_digest(str(marker.get("ref") or ""), intent_ref):
            continue
        if str(marker.get("sku") or "") != sku:
            return None
        completed_by = str(marker.get("completed_customer_ref") or "")
        if completed_by and completed_by != customer_ref:
            return None
        return marker
    return None


def _mark_stock_alert_intent_complete(
    request,
    *,
    intent_ref: str,
    customer_ref: str,
    subscription_ref: str,
) -> None:
    """Keep a completed proof replayable only by the same customer until TTL."""
    session = getattr(request, "session", None)
    if session is None:
        return
    intents = _active_stock_alert_intents(session)
    for marker in intents:
        if secrets.compare_digest(str(marker.get("ref") or ""), intent_ref):
            marker["completed_customer_ref"] = customer_ref
            marker["completed_subscription_ref"] = subscription_ref
            session[_STOCK_ALERT_INTENTS_SESSION_KEY] = intents
            return


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
class StockAlertIntentView(APIView):
    """Capture one explicit 18+ disclosure before authentication.

    The session marker contains no identity or contact data. It only proves that
    this browser explicitly accepted the current disclosure for this SKU, so a
    successful login can resume the same action without asking twice.
    """

    authentication_classes = [SessionAuthentication]
    permission_classes = [AllowAny]

    @extend_schema(
        tags=["availability"],
        summary="Prepare a short-lived product alert consent proof",
        request=StockAlertIntentRequestSerializer,
        responses={200: StockAlertIntentResponseSerializer},
    )
    def post(self, request, sku):
        if getattr(request, "limited", False):
            return Response(
                {"detail": "Muitas tentativas. Aguarde um instante."},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )
        if not catalog_service.product_exists(sku):
            raise Http404

        adult_declaration = str(request.data.get("adult_declared") or "").strip().lower()
        if adult_declaration not in {"true", "1"}:
            return Response(
                {
                    "detail": "Confirme que você tem 18 anos ou mais para receber este aviso.",
                    "field": "adult_declared",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        session = getattr(request, "session", None)
        if session is None:
            return _no_store_response(
                {"detail": "Não foi possível guardar este aviso. Tente de novo."},
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        from django.utils import timezone

        now = time.time()
        intent_ref = secrets.token_urlsafe(24)
        intents = [
            marker
            for marker in _active_stock_alert_intents(session)
            if str(marker.get("sku") or "") != sku
        ]
        intents.append(
            {
                "ref": intent_ref,
                "sku": sku,
                "created_at": now,
                "adult_declared": True,
                "adult_declared_at": timezone.now().isoformat(),
                "disclosure_version": _STOCK_ALERT_DISCLOSURE_VERSION,
            }
        )
        session[_STOCK_ALERT_INTENTS_SESSION_KEY] = intents[-_STOCK_ALERT_INTENT_LIMIT:]

        expires_at = timezone.now() + timedelta(seconds=_STOCK_ALERT_INTENT_TTL_SECONDS)
        return _no_store_response(
            {"ok": True, "intent_ref": intent_ref, "expires_at": expires_at.isoformat()},
            status_code=status.HTTP_200_OK,
        )


@method_decorator(ratelimit(key="user_or_ip", rate="10/m", method="POST", block=False), name="dispatch")
class StockAlertSubscribeView(APIView):
    """POST /api/v1/availability/<sku>/notify/ — "Me avise quando…".

    A assinatura persistente só é criada para cliente autenticado e usa o
    telefone da identidade canônica. Uma sessão anônima recebe a próxima ação,
    mas não cria opt-in: digitar um número não prova que ele pertence a quem
    está navegando.

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
        summary="Recover the current session's product alert management link",
        responses={200: StockAlertSessionStateSerializer},
    )
    def get(self, request, sku):
        """Recover only an exact alert already owned by this browser session.

        The subscription ref comes from the server-side session and is still
        checked against SKU and contact before a capability is minted.  A ref
        supplied by the caller never authorizes access.
        """
        from shopman.storefront.services import stock_alerts

        session = getattr(request, "session", None)
        markers = session.get("stock_alert_subscriptions", []) if session is not None else []
        markers = list(markers) if isinstance(markers, (list, tuple)) else []
        for marker in reversed(markers):
            if not isinstance(marker, dict) or str(marker.get("sku") or "") != sku:
                continue
            sub = stock_alerts.subscription_for_owner(
                marker.get("ref"),
                sku=sku,
                phone=str(marker.get("contact_phone") or ""),
            )
            if sub is not None:
                return _no_store_response(
                    {
                        "active": sub.is_active,
                        "management_url": stock_alerts.management_url(sub),
                    },
                    status_code=status.HTTP_200_OK,
                )
        return _no_store_response(
            {"detail": "Aviso não encontrado nesta sessão."},
            status_code=status.HTTP_404_NOT_FOUND,
        )

    @extend_schema(
        tags=["availability"],
        summary="Subscribe to a persistent product alert",
        request=StockAlertSubscribeRequestSerializer,
        responses={
            200: StockAlertSubscribeResponseSerializer,
            401: StockAlertAuthRequiredResponseSerializer,
        },
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
        from shopman.storefront.models import StockAlertSubscription
        from shopman.storefront.services import stock_alerts

        alert_type = str(request.data.get("alert_type") or "").strip()
        intent_ref = str(request.data.get("intent_ref") or "").strip()
        if alert_type and alert_type not in StockAlertSubscription.AlertType.values:
            return Response(
                {"detail": "Tipo de aviso desconhecido.", "field": "alert_type"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        customer = get_authenticated_customer(request)
        if customer is None:
            # Nenhuma linha é criada e qualquer telefone enviado pelo cliente é
            # deliberadamente ignorado: texto livre não comprova posse.
            return _no_store_response(
                {
                    "detail": "Entre para confirmar seu WhatsApp e ativar este aviso.",
                    "field": "auth",
                    "auth_required": True,
                },
                status_code=status.HTTP_401_UNAUTHORIZED,
            )

        intent = (
            _stock_alert_intent(
                request,
                sku=sku,
                intent_ref=intent_ref,
                customer_ref=str(customer.ref),
            )
            if intent_ref
            else None
        )
        if intent_ref and intent is None:
            return _no_store_response(
                {
                    "detail": "Este pedido de aviso expirou. Toque em Me avise para tentar de novo.",
                    "field": "intent_ref",
                },
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        adult_declaration = str(request.data.get("adult_declared") or "").strip().lower()
        if intent is None and adult_declaration not in {"true", "1"}:
            return Response(
                {
                    "detail": "Confirme que você tem 18 anos ou mais para receber este aviso.",
                    "field": "adult_declared",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        from shopman.shop.services.marketing_age import is_known_minor

        if is_known_minor(getattr(customer, "birthday", None)):
            return Response(
                {
                    "detail": (
                        "Este aviso está disponível somente para pessoas com 18 anos ou mais. "
                        "A data de nascimento da sua conta indica idade inferior a 18 anos."
                    ),
                    "field": "birthday",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # A repetição de uma intenção já concluída é somente uma leitura do
        # resultado original. Ela nunca executa o opt-in novamente: assim uma
        # resposta HTTP perdida não pode desfazer uma pausa ou recriar algo que
        # a pessoa cancelou logo depois em outra aba/dispositivo.
        completed_subscription_ref = str((intent or {}).get("completed_subscription_ref") or "")
        if intent is not None and str(intent.get("completed_customer_ref") or ""):
            try:
                completed_sub = StockAlertSubscription.objects.filter(
                    ref=uuid.UUID(completed_subscription_ref),
                    sku=sku,
                    customer_ref=customer.ref,
                    purpose="stock_availability",
                    proof_status="verified",
                ).first()
            except (TypeError, ValueError):
                completed_sub = None
            if completed_sub is None:
                return _no_store_response(
                    {
                        "detail": "Este pedido de aviso não corresponde mais ao resultado original.",
                        "field": "intent_ref",
                    },
                    status_code=status.HTTP_400_BAD_REQUEST,
                )
            replay = {
                "ok": True,
                "subscription_ref": str(completed_sub.ref),
                "active": completed_sub.is_active,
                "expires_at": completed_sub.expires_at.isoformat() if completed_sub.expires_at else None,
            }
            if completed_sub.revoked_at is None:
                replay["management_url"] = stock_alerts.management_url(completed_sub)
            return _no_store_response(replay, status_code=status.HTTP_200_OK)

        channel_ref = request.GET.get("channel") or STOREFRONT_CHANNEL_REF
        # A sessão autenticada usa sempre o contato da identidade canônica;
        # um telefone no corpo não pode redirecionar o aviso.

        outcome = stock_alerts.subscribe_with_outcome(
            sku,
            channel_ref=channel_ref,
            customer=customer,
            phone="",
            alert_type=alert_type,
            adult_declared=True,
            resume_existing=False,
        )
        sub = outcome.subscription
        if sub is None:
            return Response(
                {"detail": "Não foi possível registrar o aviso."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        # Mantém o marcador de sessão compatível com capacidades já emitidas; a
        # identidade autenticada continua sendo a autoridade para esta criação.
        session = getattr(request, "session", None)
        marked: list[dict] = []
        if session is not None:
            session.pop("stock_alert_skus", None)
            marked = session.get("stock_alert_subscriptions")
            marked = list(marked) if isinstance(marked, (list, tuple)) else []

        # subscribe_with_outcome deliberately leaves an existing paused row
        # untouched. This explicit repeat opt-in belongs to its authenticated
        # customer and may resume it for future occurrences.
        if sub.paused_at is not None:
            stock_alerts.set_paused(
                sub.ref,
                paused=False,
                sku=sub.sku,
                customer=customer,
            )
            sub.refresh_from_db()

        if session is not None:
            marker = {
                "ref": str(sub.ref),
                "sku": sub.sku,
                "alert_type": sub.alert_type,
                "contact_phone": sub.contact_phone,
            }
            if marker not in marked:
                marked.append(marker)
                session["stock_alert_subscriptions"] = marked

        if intent_ref:
            _mark_stock_alert_intent_complete(
                request,
                intent_ref=intent_ref,
                customer_ref=str(customer.ref),
                subscription_ref=str(sub.ref),
            )

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


def _marker_for_subscription(markers: list[dict], sub) -> dict | None:
    """Return the exact trusted session marker for ``sub``, if present."""

    for marker in markers:
        if not isinstance(marker, dict):
            continue
        if (
            str(marker.get("ref") or "") == str(sub.ref)
            and str(marker.get("sku") or "") == str(sub.sku)
            and str(marker.get("alert_type") or "") == str(sub.alert_type)
            and str(marker.get("contact_phone") or "") == str(sub.contact_phone)
        ):
            return marker
    return None


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
