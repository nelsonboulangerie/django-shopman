"""Backstage API — notificações pessoais do operador.

GET  /api/v1/backstage/notifications/             → não lidas do usuário atual
POST /api/v1/backstage/notifications/<pk>/read/   → marcar como lida
POST /api/v1/backstage/notifications/<pk>/action/ → tombstone do atalho legado

Diferente de ``alerts.py``, que é da LOJA (qualquer operador vê o mesmo painel),
isto é da PESSOA: o gestor recebe o pedido de aprovação onde estiver. Por isso
todo queryset é filtrado por ``request.user`` — nem staff lê a caixa alheia.
"""

from __future__ import annotations

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
    Announcement,
    NotificationLifecycle,
    NotificationSeverity,
    UserNotification,
)
from shopman.shop.models.user_notification import ACTIVE_NOTIFICATION_STATES
from shopman.shop.services import user_notifications as notification_lifecycle
from shopman.shop.services.marketing_time import configured_timezone_name

from .permissions import IsBackstageOperator

_DEFAULT_LIMIT = 20
_MAX_LIMIT = 100
_V2_COLLECTION = "operator_notifications.v2"

#: Ações que uma notificação acionável pode disparar.
ACTION_APPROVE = "approve"
ACTION_REJECT = "reject"


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
    """Tombstone do atalho inseguro; decisões migraram para o objeto canônico."""

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
        if action not in (ACTION_APPROVE, ACTION_REJECT):
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
