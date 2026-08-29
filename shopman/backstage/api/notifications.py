"""Backstage API — notificações pessoais do operador.

GET  /api/v1/backstage/notifications/             → não lidas do usuário atual
POST /api/v1/backstage/notifications/<pk>/read/   → marcar como lida
POST /api/v1/backstage/notifications/<pk>/action/ → executar a ação acionável

Diferente de ``alerts.py``, que é da LOJA (qualquer operador vê o mesmo painel),
isto é da PESSOA: o gestor recebe o pedido de aprovação onde estiver. Por isso
todo queryset é filtrado por ``request.user`` — nem staff lê a caixa alheia.
"""

from __future__ import annotations

import logging

from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema, extend_schema_view
from rest_framework.response import Response
from rest_framework.views import APIView

from shopman.shop.models import UserNotification

from .permissions import IsBackstageOperator

logger = logging.getLogger(__name__)

_DEFAULT_LIMIT = 20
_MAX_LIMIT = 100

#: Ações que uma notificação acionável pode disparar.
ACTION_APPROVE = "approve"
ACTION_REJECT = "reject"
#: "Não fui eu": o dono não reconhece o acesso e derruba as sessões da conta.
ACTION_NOT_ME = "not_me"

_CAMPAIGN_ACTIONS = (ACTION_APPROVE, ACTION_REJECT)


def _notification_dict(notification: UserNotification) -> dict:
    return {
        "pk": notification.pk,
        "category": notification.category,
        "title": notification.title,
        "message": notification.message,
        "action_url": notification.action_url,
        "action_data": notification.action_data or {},
        "is_actionable": notification.is_actionable,
        "is_read": notification.is_read,
        "created_at": notification.created_at.isoformat(),
        "created_at_display": timezone.localtime(notification.created_at).strftime(
            "%d/%m às %H:%M"
        ),
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
        queryset = _own(request)
        if not _flag(request, "all"):
            queryset = queryset.filter(is_read=False)

        limit = _limit(request)
        notifications = list(queryset[:limit])
        return Response({
            "notifications": [_notification_dict(n) for n in notifications],
            "unread_count": _own(request).filter(is_read=False).count(),
            "actionable_count": _own(request)
            .filter(is_read=False, is_actionable=True)
            .count(),
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
        notification.mark_read()
        return Response({"ok": True, "pk": pk, "unread_count": _unread(request)})


@extend_schema_view(
    post=extend_schema(
        tags=["backstage"],
        summary="Execute a notification's action (e.g. approve an announcement)",
        responses={200: OpenApiResponse(description="Action executed.")},
    ),
)
class NotificationActionView(APIView):
    """Executar a decisão pedida pela notificação, sem sair de onde se está.

    Duas famílias: campanha (aprovar/descartar um anúncio) e acesso ("não fui
    eu", que derruba as sessões da conta). A ação marca a notificação como lida
    no sucesso — a decisão já foi tomada, o card sai da caixa.

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
        if not notification.is_actionable:
            return Response(
                {"detail": "Esta notificação não pede nenhuma ação."}, status=400
            )

        action = str(request.data.get("action") or ACTION_APPROVE).strip()
        if action == ACTION_NOT_ME:
            return self._not_me(request, notification)
        if action not in _CAMPAIGN_ACTIONS:
            return Response(
                {"detail": "Ação desconhecida.", "field": "action"}, status=400
            )

        announcement_id = (notification.action_data or {}).get("announcement_id")
        if not announcement_id:
            return Response(
                {"detail": "Esta notificação não aponta para nenhum announcement."}, status=400
            )

        if not request.user.has_perm("shop.manage_campaigns"):
            return Response(
                {"detail": "Você não tem permissão para publicar."}, status=403
            )

        from shopman.shop.services import campaign

        try:
            announcement = (
                campaign.approve(announcement_id, request.user)
                if action == ACTION_APPROVE
                else campaign.reject(announcement_id, request.user)
            )
        except campaign.CampaignError as exc:
            # Vencido, recusado, já publicado ou inexistente: em todos, a notificação
            # perdeu o sentido, então some da caixa junto com o erro. A mensagem do
            # serviço diz qual dos casos foi.
            notification.mark_read()
            return Response({"detail": str(exc)}, status=400)

        notification.mark_read()
        logger.info(
            "notification.action user=%s action=%s announcement=%s", request.user.pk, action, announcement_id
        )
        return Response({
            "ok": True,
            "action": action,
            "announcement_id": announcement.pk,
            "status": announcement.status,
            "unread_count": _unread(request),
        })


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


def _flag_body(request, name: str) -> bool:
    return str((request.data or {}).get(name) or "").lower() in ("1", "true", "yes")


def _unread(request) -> int:
    return _own(request).filter(is_read=False).count()


def _limit(request) -> int:
    raw = request.query_params.get("limit")
    try:
        return max(1, min(int(raw), _MAX_LIMIT)) if raw else _DEFAULT_LIMIT
    except (TypeError, ValueError):
        return _DEFAULT_LIMIT


def _flag(request, name: str) -> bool:
    return str(request.query_params.get(name) or "").lower() in ("1", "true", "yes")
