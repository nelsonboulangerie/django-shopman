"""Backstage API — notificações pessoais do operador.

GET  /api/v1/backstage/notifications/             → não lidas do usuário atual
POST /api/v1/backstage/notifications/<pk>/read/   → marcar como lida
POST /api/v1/backstage/notifications/<pk>/action/ → tombstone do atalho legado

Diferente de ``alerts.py``, que é da LOJA (qualquer operador vê o mesmo painel),
isto é da PESSOA: o gestor recebe o pedido de aprovação onde estiver. Por isso
todo queryset é filtrado por ``request.user`` — nem staff lê a caixa alheia.
"""

from __future__ import annotations

import logging

from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema, extend_schema_view
from rest_framework.response import Response
from rest_framework.views import APIView

from shopman.backstage.api.marketing_cursor import (
    InvalidMarketingCursor,
    MarketingCursor,
    decode_cursor,
    encode_cursor,
    first_cursor,
)
from shopman.backstage.api.projections import projection_data
from shopman.backstage.projections.marketing_actions import (
    resolve_notification_actions_for,
)
from shopman.shop.models import (
    PUSH_SURFACE_CATEGORIES,
    Announcement,
    NotificationCategory,
    NotificationLifecycle,
    NotificationSeverity,
    PushSubscription,
    PushSurface,
    UserNotification,
)
from shopman.shop.models.user_notification import ACTIVE_NOTIFICATION_STATES
from shopman.shop.services import user_notifications as notification_lifecycle
from shopman.shop.services.marketing_time import configured_timezone_name
from shopman.shop.services.push_endpoints import normalize_push_endpoint

from .permissions import IsBackstageOperator

logger = logging.getLogger(__name__)

_DEFAULT_LIMIT = 20
_MAX_LIMIT = 100
_V2_COLLECTION = "operator_notifications.v2"

#: Ações que uma notificação acionável pode disparar.
ACTION_APPROVE = "approve"
ACTION_REJECT = "reject"
#: "Não fui eu": o dono não reconhece o acesso e derruba as sessões da conta.
ACTION_NOT_ME = "not_me"

_CAMPAIGN_ACTIONS = (ACTION_APPROVE, ACTION_REJECT)


def _notification_dict(
    notification: UserNotification,
    *,
    actions,
) -> dict:
    return {
        "pk": notification.pk,
        "category": notification.category,
        "title": notification.title,
        "message": notification.message,
        "action_url": notification.action_url,
        "action_data": notification.action_data or {},
        "is_actionable": notification.is_actionable,
        "is_read": notification.is_read,
        "lifecycle": notification.lifecycle,
        "severity": notification.severity,
        "source": {
            "condition": notification.source_condition,
            "ref": notification.source_ref,
            "version": notification.source_version,
        },
        "owner": {
            "user_id": notification.user_id,
            "role": notification.owner_role,
        },
        "escalation": {
            "role": notification.escalation_role,
            "at": notification.escalates_at.isoformat() if notification.escalates_at else None,
        },
        "expires_at": notification.expires_at.isoformat() if notification.expires_at else None,
        "seen_at": notification.read_at.isoformat() if notification.read_at else None,
        "acknowledged_at": (
            notification.acknowledged_at.isoformat()
            if notification.acknowledged_at
            else None
        ),
        "resolved_at": notification.resolved_at.isoformat() if notification.resolved_at else None,
        "version": notification.version,
        "created_at": notification.created_at.isoformat(),
        "created_at_display": timezone.localtime(notification.created_at).strftime(
            "%d/%m às %H:%M"
        ),
        "actions": projection_data(actions),
    }


def _own(request):
    """Só a caixa de quem está pedindo. Nunca aceitar user_id do cliente."""
    return UserNotification.objects.filter(user=request.user)


@extend_schema_view(
    get=extend_schema(
        tags=["backstage"],
        summary="Personal notifications for the current user",
        parameters=[
            OpenApiParameter("limit", int, description="Máximo de itens (default 20)."),
            OpenApiParameter("all", bool, description="Inclui as já lidas."),
        ],
        responses={200: OpenApiResponse(description="Notifications, newest first.")},
    ),
)
class NotificationListView(APIView):
    permission_classes = [IsBackstageOperator]

    def get(self, request):
        # Um push perdido não deixa card zumbi: o fetch sempre reconcilia com a
        # condição canônica antes de projetar a caixa do owner.
        notification_lifecycle.reconcile_user_notifications(user=request.user)
        queryset = _own(request)
        if not _flag(request, "all"):
            queryset = queryset.filter(is_read=False)

        limit = _limit(request)
        notifications = list(queryset[:limit])
        announcement_ids = {
            announcement_id
            for notification in notifications
            if (announcement_id := _announcement_id(notification)) is not None
        }
        announcements = {
            announcement.pk: announcement
            for announcement in Announcement.objects.filter(pk__in=announcement_ids).only(
                "pk",
                "version",
                "status",
                "expires_at",
            )
        }
        actions = resolve_notification_actions_for(
            notifications,
            actor=request.user,
            announcements=announcements,
        )
        return Response({
            "notifications": [
                _notification_dict(
                    notification,
                    actions=actions[notification.pk],
                )
                for notification in notifications
            ],
            "unread_count": _own(request).filter(is_read=False).count(),
            # Campo v1 preservado até o MKT-037 trocar o cliente. O contador
            # canônico que não confunde seen com resolved é ``unresolved_count``.
            "actionable_count": _own(request)
            .filter(is_read=False, is_actionable=True)
            .count(),
            "unseen_count": _unseen(request),
            "unresolved_count": _unresolved(request),
        })


@extend_schema_view(
    get=extend_schema(
        tags=["backstage"],
        summary="Condition-backed personal alerts for the current user",
        parameters=[
            OpenApiParameter("limit", int, description="Máximo de itens (default 20)."),
            OpenApiParameter("cursor", str, description="Cursor opaco da página anterior."),
            OpenApiParameter("history", bool, description="Inclui alertas fechados e informativos."),
        ],
        responses={200: OpenApiResponse(description="Stable owner-scoped alert page.")},
    ),
)
class NotificationListV2View(APIView):
    """Caixa v2 estável; o v1 permanece até a troca do cliente no MKT-037."""

    permission_classes = [IsBackstageOperator]

    def get(self, request):
        notification_lifecycle.reconcile_user_notifications(user=request.user)
        limit = _limit(request)
        raw_cursor = str(request.query_params.get("cursor") or "").strip()
        try:
            cursor = (
                decode_cursor(raw_cursor, collection=_V2_COLLECTION)
                if raw_cursor
                else first_cursor(collection=_V2_COLLECTION)
            )
        except InvalidMarketingCursor:
            return Response(
                {
                    "detail": "O cursor de alertas não é válido.",
                    "field": "cursor",
                    "errors": {"cursor": ["Solicite a primeira página novamente."]},
                },
                status=422,
            )

        queryset = _own(request).filter(
            created_at__lte=cursor.as_of,
            retention_until__gt=cursor.as_of,
        )
        if not _flag(request, "history"):
            queryset = queryset.filter(
                lifecycle__in=ACTIVE_NOTIFICATION_STATES,
            ).exclude(severity=NotificationSeverity.INFORMATION)
        if cursor.created_at is not None and cursor.pk is not None:
            queryset = queryset.filter(
                Q(created_at__lt=cursor.created_at)
                | Q(created_at=cursor.created_at, pk__lt=cursor.pk)
            )

        rows = list(queryset.order_by("-created_at", "-pk")[: limit + 1])
        has_more = len(rows) > limit
        page_rows = rows[:limit]
        next_cursor = ""
        if has_more:
            last = page_rows[-1]
            next_cursor = encode_cursor(MarketingCursor(
                collection=_V2_COLLECTION,
                as_of=cursor.as_of,
                created_at=last.created_at,
                pk=last.pk,
            ))

        announcement_ids = {
            announcement_id
            for notification in page_rows
            if (announcement_id := _announcement_id(notification)) is not None
        }
        announcements = {
            announcement.pk: announcement
            for announcement in Announcement.objects.filter(pk__in=announcement_ids).only(
                "pk",
                "version",
                "status",
                "expires_at",
            )
        }
        actions = resolve_notification_actions_for(
            page_rows,
            actor=request.user,
            announcements=announcements,
        )
        return Response({
            "schema_version": 2,
            "shop_timezone": configured_timezone_name(),
            "as_of": cursor.as_of.isoformat(),
            "notifications": [
                _notification_dict(notification, actions=actions[notification.pk])
                for notification in page_rows
            ],
            "page": {
                "limit": limit,
                "has_more": has_more,
                "next_cursor": next_cursor,
            },
            "counts": {
                "unseen": _unseen(request),
                "unresolved": _unresolved(request),
            },
        })


@extend_schema_view(
    post=extend_schema(
        tags=["backstage"],
        summary="Mark a notification as read",
        responses={200: OpenApiResponse(description="Notification marked as read.")},
    ),
)
class NotificationReadView(APIView):
    permission_classes = [IsBackstageOperator]

    def post(self, request, pk: int):
        notification = _own(request).filter(pk=pk).first()
        if notification is None:
            return Response({"detail": "Notificação não encontrada."}, status=404)
        notification = notification_lifecycle.mark_seen(
            notification_id=notification.pk,
            actor=request.user,
        )
        return Response({
            "ok": True,
            "pk": pk,
            "lifecycle": notification.lifecycle,
            "unread_count": _unread(request),
            "unseen_count": _unseen(request),
            "unresolved_count": _unresolved(request),
        })


@extend_schema_view(
    post=extend_schema(
        tags=["backstage"],
        summary="Acknowledge ownership of a notification condition",
        responses={200: OpenApiResponse(description="Notification acknowledged.")},
    ),
)
class NotificationAcknowledgeView(APIView):
    permission_classes = [IsBackstageOperator]

    def post(self, request, pk: int):
        notification = _own(request).filter(pk=pk).first()
        if notification is None:
            return Response({"detail": "Notificação não encontrada."}, status=404)
        notification = notification_lifecycle.acknowledge(
            notification_id=notification.pk,
            actor=request.user,
        )
        return Response({
            "ok": True,
            "pk": pk,
            "lifecycle": notification.lifecycle,
            "unseen_count": _unseen(request),
            "unresolved_count": _unresolved(request),
        })


@extend_schema_view(
    post=extend_schema(
        tags=["backstage"],
        summary="Mark the currently visible notification page as seen",
        responses={200: OpenApiResponse(description="Unseen notifications marked as seen.")},
    ),
)
class NotificationSeenBatchView(APIView):
    permission_classes = [IsBackstageOperator]

    def post(self, request):
        raw_ids = request.data.get("notification_ids")
        if not isinstance(raw_ids, list) or len(raw_ids) > _MAX_LIMIT:
            return Response(
                {
                    "detail": "Envie uma lista de até 100 alertas visíveis.",
                    "field": "notification_ids",
                    "errors": {"notification_ids": ["Lista inválida."]},
                },
                status=400,
            )
        if any(
            not isinstance(value, int) or isinstance(value, bool) or value <= 0
            for value in raw_ids
        ):
            return Response(
                {
                    "detail": "A lista contém um identificador inválido.",
                    "field": "notification_ids",
                    "errors": {"notification_ids": ["Use apenas inteiros positivos."]},
                },
                status=400,
            )
        changed = notification_lifecycle.mark_seen_many(
            notification_ids=raw_ids,
            actor=request.user,
        )
        return Response({
            "ok": True,
            "changed": changed,
            "unseen_count": _unseen(request),
            "unresolved_count": _unresolved(request),
        })


@extend_schema_view(
    post=extend_schema(
        tags=["backstage"],
        summary="Reject legacy inline decisions and point to the canonical object",
        responses={410: OpenApiResponse(description="Decision moved to the announcement.")},
    ),
)
class NotificationActionView(APIView):
    """Handle account safety here; move Marketing decisions to the canonical object.

    Account access alerts keep the authenticated ``not_me`` action. Campaign
    approve/reject shortcuts are tombstones: version, idempotency and consequence
    confirmation now live on the announcement itself.

    ⚠️ **A ação mora aqui, dentro da superfície autenticada, e nunca num link.**
    Se um dia o aviso de acesso sair por WhatsApp ou e-mail, a mensagem só pode
    dizer "abra o app": um botão "clique aqui para bloquear" dentro de uma
    mensagem é phishing pronto, e seria a nossa própria comunicação ensinando o
    operador a clicar nele. Aqui há sessão, ``request.user`` provado e dono
    conferido; num link não há nada disso.
    """

    permission_classes = [IsBackstageOperator]

    def post(self, request, pk: int):
        notification = _own(request).filter(pk=pk).first()
        if notification is None:
            return Response({"detail": "Notificação não encontrada."}, status=404)
        raw_action = request.data.get("action")
        if not isinstance(raw_action, str) or not raw_action.strip():
            return Response(
                {
                    "detail": "Escolha explicitamente uma ação.",
                    "field": "action",
                    "errors": {"action": ["Ação obrigatória."]},
                    "code": "action_required",
                },
                status=400,
            )
        action = raw_action.strip()
        if action == ACTION_NOT_ME:
            return self._not_me(request, notification)
        if action not in _CAMPAIGN_ACTIONS:
            return Response(
                {"detail": "Ação desconhecida.", "field": "action"}, status=400
            )

        announcement_id = _announcement_id(notification)
        if announcement_id is None:
            return Response(
                {"detail": "Esta notificação não aponta para nenhum announcement."}, status=400
            )

        notification_lifecycle.record_action(
            notification_id=notification.pk,
            actor=request.user,
            action_code=action,
        )

        # Aprovar/recusar precisa de versão, idempotência, consequência e gates
        # do command moderno. O alerta só conduz ao contexto; nunca os contorna.
        return Response(
            {
                "detail": "A decisão agora é feita no anúncio, com a versão e a consequência visíveis.",
                "code": "notification_action_moved",
                "action": {
                    "kind": "open_announcement",
                    "href": f"/announcements/{announcement_id}#review",
                },
            },
            status=410,
        )


    def _not_me(self, request, notification):
        """Derrubar as sessões da conta porque o dono não reconhece o acesso.

        Exige ``confirm: true`` **explícito**. É ação destrutiva: uma venda em
        curso naquele terminal cai junto, e a tela precisa ter dito isso antes.
        Sem a confirmação, a resposta descreve o estrago em vez de causá-lo.
        """
        from shopman.backstage.models import SignInEvent
        from shopman.backstage.services import sign_in_audit

        event_id = (notification.action_data or {}).get("sign_in_event_id")
        if not event_id:
            return Response(
                {"detail": "Este aviso não aponta para nenhum acesso.", "field": "action"},
                status=400,
            )
        # `user=request.user` no filtro, e não só no `get`: um id de acesso
        # alheio não pode virar uma revogação alheia por adivinhação.
        event = SignInEvent.objects.filter(pk=event_id, user=request.user).first()
        if event is None:
            return Response({"detail": "Acesso não encontrado."}, status=404)

        if not _flag_body(request, "confirm"):
            return Response(
                {
                    "ok": False,
                    "needs_confirmation": True,
                    "detail": (
                        "Isto encerra as sessões abertas da sua conta em outros "
                        "dispositivos e invalida o seu crachá. Uma venda em andamento "
                        "naquele terminal será perdida. Seu PIN continua valendo."
                    ),
                },
                status=409,
            )

        try:
            resultado = sign_in_audit.revoke_access(
                user=request.user, requested_by=request.user,
                reason=sign_in_audit.REASON_NOT_ME, event=event, request=request,
            )
        except sign_in_audit.RevokeError as exc:
            return Response({"detail": str(exc), "error": {"code": exc.code}}, status=400)

        notification.mark_read()
        logger.warning(
            "notification.not_me user=%s event=%s sessions=%s",
            request.user.pk, event.pk, resultado["sessions_revoked"],
        )
        return Response({
            "ok": True,
            "action": ACTION_NOT_ME,
            **resultado,
            "unread_count": _unread(request),
        })


@extend_schema_view(
    get=extend_schema(
        tags=["backstage"],
        summary="List Web Push devices and category choices for the current user",
        responses={200: OpenApiResponse(description="Active devices and category choices.")},
    ),
    post=extend_schema(
        tags=["backstage"],
        summary="Register or refresh a Web Push subscription",
        responses={200: OpenApiResponse(description="Subscription registered.")},
    ),
    patch=extend_schema(
        tags=["backstage"],
        summary="Update Web Push categories for one owned device",
        responses={200: OpenApiResponse(description="Subscription preferences updated.")},
    ),
    delete=extend_schema(
        tags=["backstage"],
        summary="Remove one owned Web Push device",
        responses={204: OpenApiResponse(description="Subscription removed.")},
    ),
)
class NotificationPushSubscriptionView(APIView):
    """Assinaturas da pessoa autenticada; IDs/endpoints alheios sempre viram 404."""

    permission_classes = [IsBackstageOperator]

    def get(self, request):
        devices = PushSubscription.objects.filter(
            user=request.user,
            disabled_at__isnull=True,
        ).order_by("-created_at", "-pk")
        labels = dict(NotificationCategory.choices)
        return Response({
            "devices": [_push_subscription_dict(subscription) for subscription in devices],
            "categories": [
                {"value": category, "label": labels[category]}
                for category in sorted(PUSH_SURFACE_CATEGORIES[PushSurface.HUB])
            ],
            "surface_categories": {
                surface: sorted(categories)
                for surface, categories in PUSH_SURFACE_CATEGORIES.items()
            },
        })

    def post(self, request):
        payload = request.data or {}
        raw_subscription = payload.get("subscription")
        subscription = raw_subscription if isinstance(raw_subscription, dict) else payload
        endpoint = _valid_push_endpoint(subscription.get("endpoint"))
        if endpoint is None:
            return _push_error("endpoint", "Envie um endpoint HTTPS válido.")

        keys = subscription.get("keys")
        if not isinstance(keys, dict):
            return _push_error("keys", "Envie as chaves p256dh e auth do navegador.")
        p256dh = _bounded_text(keys.get("p256dh"), maximum=512)
        auth = _bounded_text(keys.get("auth"), maximum=512)
        if not p256dh or not auth:
            return _push_error("keys", "As chaves p256dh e auth são obrigatórias.")

        surface_ref = _bounded_text(payload.get("surface_ref"), maximum=32)
        if surface_ref not in PushSurface.values:
            return _push_error("surface_ref", "Esta surface não aceita Web Push.")
        categories = _valid_push_categories(payload.get("categories"), surface_ref=surface_ref)
        if categories is None:
            return _push_error("categories", "Uma categoria não pertence a esta surface.")
        device_label = _bounded_text(payload.get("device_label"), maximum=120) or "Este dispositivo"

        with transaction.atomic():
            record, created = PushSubscription.objects.update_or_create(
                endpoint=endpoint,
                defaults={
                    "user": request.user,
                    "p256dh": p256dh,
                    "auth": auth,
                    "surface_ref": surface_ref,
                    "device_label": device_label,
                    "categories": categories,
                    "failures": 0,
                    "disabled_at": None,
                },
            )
        return Response(
            {"created": created, "device": _push_subscription_dict(record)},
            status=201 if created else 200,
        )

    def patch(self, request):
        record = _owned_push_subscription(request)
        if record is None:
            return Response({"detail": "Dispositivo não encontrado."}, status=404)
        categories = _valid_push_categories(
            (request.data or {}).get("categories"),
            surface_ref=record.surface_ref,
        )
        if categories is None:
            return _push_error("categories", "Uma categoria não pertence a esta surface.")
        record.categories = categories
        record.save(update_fields=["categories"])
        return Response({"device": _push_subscription_dict(record)})

    def delete(self, request):
        record = _owned_push_subscription(request)
        if record is None:
            return Response({"detail": "Dispositivo não encontrado."}, status=404)
        if record.disabled_at is None:
            record.disabled_at = timezone.now()
            record.save(update_fields=["disabled_at"])
        return Response(status=204)


def _push_subscription_dict(subscription: PushSubscription) -> dict:
    return {
        "id": subscription.pk,
        "endpoint": subscription.endpoint,
        "surface_ref": subscription.surface_ref,
        "device_label": subscription.device_label,
        "categories": list(subscription.categories or []),
        "created_at": subscription.created_at.isoformat(),
        "last_success_at": (
            subscription.last_success_at.isoformat() if subscription.last_success_at else None
        ),
    }


def _owned_push_subscription(request) -> PushSubscription | None:
    payload = request.data or {}
    queryset = PushSubscription.objects.filter(user=request.user, disabled_at__isnull=True)
    raw_id = payload.get("id")
    if isinstance(raw_id, int) and not isinstance(raw_id, bool) and raw_id > 0:
        return queryset.filter(pk=raw_id).first()
    endpoint = _bounded_text(payload.get("endpoint"), maximum=4096)
    return queryset.filter(endpoint=endpoint).first() if endpoint else None


def _valid_push_endpoint(value) -> str | None:
    return normalize_push_endpoint(value)


def _valid_push_categories(value, *, surface_ref: str) -> list[str] | None:
    allowed = PUSH_SURFACE_CATEGORIES.get(surface_ref)
    if allowed is None or not isinstance(value, list) or len(value) > len(PUSH_SURFACE_CATEGORIES[PushSurface.HUB]):
        return None
    categories = [_bounded_text(category, maximum=32) for category in value]
    if any(not category or category not in allowed for category in categories):
        return None
    if len(categories) != len(set(categories)):
        return None
    return sorted(categories)


def _bounded_text(value, *, maximum: int) -> str:
    if not isinstance(value, str):
        return ""
    normalized = value.strip()
    return normalized if len(normalized) <= maximum else ""


def _push_error(field: str, detail: str) -> Response:
    return Response(
        {"detail": detail, "field": field, "errors": {field: [detail]}},
        status=400,
    )


def _flag_body(request, name: str) -> bool:
    return str((request.data or {}).get(name) or "").lower() in ("1", "true", "yes")


def _unread(request) -> int:
    return _own(request).filter(is_read=False).count()


def _unseen(request) -> int:
    return _own(request).filter(
        lifecycle=NotificationLifecycle.UNSEEN,
    ).exclude(severity=NotificationSeverity.INFORMATION).count()


def _unresolved(request) -> int:
    return _own(request).filter(
        lifecycle__in=ACTIVE_NOTIFICATION_STATES,
    ).exclude(severity=NotificationSeverity.INFORMATION).count()


def _announcement_id(notification: UserNotification) -> int | None:
    if not notification.is_actionable or not isinstance(notification.action_data, dict):
        return None
    raw = notification.action_data.get("announcement_id")
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def _limit(request) -> int:
    raw = request.query_params.get("limit")
    try:
        return max(1, min(int(raw), _MAX_LIMIT)) if raw else _DEFAULT_LIMIT
    except (TypeError, ValueError):
        return _DEFAULT_LIMIT


def _flag(request, name: str) -> bool:
    return str(request.query_params.get(name) or "").lower() in ("1", "true", "yes")
