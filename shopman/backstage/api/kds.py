"""Backstage KDS API — JSON endpoints for the Kitchen Display System.

GET  /api/v1/backstage/kds/                       → list of KDS instances
GET  /api/v1/backstage/kds/<ref>/                 → KDS board projection
POST /api/v1/backstage/kds/tickets/<pk>/start/    → put ticket in progress
POST /api/v1/backstage/kds/tickets/<pk>/done/     → mark ticket done
POST /api/v1/backstage/kds/<ref>/seen/           → "Visto" da estação (K20)
PATCH /api/v1/backstage/kds/<ref>/settings/       → densidade e som da estação
POST /api/v1/backstage/kds/<ref>/follow/          → levar a estação no bolso (push)
POST /api/v1/backstage/kds/expedition/<pk>/printed-stations/<ref>/done/
                                                   → "Pronto" da Saída pela estação sem tela
POST /api/v1/backstage/kds/printed-tickets/<pk>/done/ → "Pronto" do PDV no card do ticket
POST /api/v1/backstage/kds/printed-tickets/scan/  → "Pronto" pelo leitor de código (QR do papel)
GET  /api/v1/backstage/kds/pickup/               → customer pickup board
"""

from __future__ import annotations

import logging

from drf_spectacular.utils import OpenApiResponse, extend_schema, extend_schema_view
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from shopman.backstage.projections.kds import (
    build_kds_board,
    build_kds_customer_status,
    build_kds_index,
    build_kds_ticket,
    build_printed_ticket_receipt,
)
from shopman.backstage.services import kds as kds_service
from shopman.backstage.services.exceptions import (
    KDSError,
    KDSInstanceNotFound,
    KDSOrderNotFound,
    KDSTicketNotFound,
)

from .permissions import HasAnyBackstagePermission, HasBackstagePermission
from .projections import projection_data

logger = logging.getLogger(__name__)


def _actor(request) -> str:
    user = getattr(request, "user", None)
    return getattr(user, "username", None) or "operator"


@extend_schema_view(
    get=extend_schema(
        tags=["backstage"],
        summary="List KDS instances",
        responses={200: OpenApiResponse(description="List of KDS instance summaries.")},
    ),
)
class KDSIndexView(APIView):
    permission_classes = [HasBackstagePermission]
    required_permission = "backstage.operate_kds"

    def get(self, request):
        instances = build_kds_index()
        return Response({"instances": projection_data(instances)})


@extend_schema_view(
    get=extend_schema(
        tags=["backstage"],
        summary="KDS board for a station",
        responses={
            200: OpenApiResponse(description="KDS board projection."),
            404: OpenApiResponse(description="Estação inexistente ou desativada."),
        },
    ),
)
class KDSBoardView(APIView):
    permission_classes = [HasBackstagePermission]
    required_permission = "backstage.operate_kds"

    def get(self, request, ref: str):
        # O quadro é sempre o de hoje: a prévia de outra data foi para a
        # Produção/Encomendas (SUITE-UX §9).
        try:
            board = build_kds_board(ref)
        except KDSInstanceNotFound:
            # Kiosk com a estação antiga (reseed, renomeada, desativada) ou o
            # endereço da Saída (que mora no Gestor): 404 no dialeto canônico, e
            # o app troca para "escolha outra estação".
            return Response(
                {"detail": "Esta estação não existe mais. Escolha outra na lista de estações."},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response({"board": projection_data(board)})


@extend_schema_view(
    post=extend_schema(
        tags=["backstage"],
        summary="Visto da estação: o aviso de pedido novo para em todas as telas dela",
        responses={200: OpenApiResponse(description="Quantos tickets ficaram vistos.")},
    ),
)
class KDSStationSeenView(APIView):
    permission_classes = [HasBackstagePermission]
    required_permission = "backstage.operate_kds"

    def post(self, request, ref: str):
        ticket_pks = request.data.get("ticket_pks")
        if not isinstance(ticket_pks, list):
            return Response(
                {"detail": "Diga quais pedidos foram vistos.", "field": "ticket_pks"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            seen = kds_service.mark_station_seen(station_ref=ref, ticket_pks=ticket_pks, actor=_actor(request))
        except KDSInstanceNotFound as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)
        return Response({"ok": True, "seen": seen})


@extend_schema_view(
    patch=extend_schema(
        tags=["backstage"],
        summary="Densidade e som da estação provisionada",
        responses={200: OpenApiResponse(description="Densidade e som gravados.")},
    ),
)
class KDSStationSettingsView(APIView):
    permission_classes = [HasBackstagePermission]
    required_permission = "backstage.operate_kds"

    def patch(self, request, ref: str):
        density = request.data.get("density")
        sound_enabled = request.data.get("sound_enabled")
        if density is not None and not isinstance(density, str):
            return Response({"detail": "Tamanho do ticket inválido.", "field": "density"}, status=status.HTTP_400_BAD_REQUEST)
        if sound_enabled is not None and not isinstance(sound_enabled, bool):
            return Response({"detail": "Som inválido.", "field": "sound_enabled"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            instance = kds_service.update_station_settings(
                station_ref=ref, density=density, sound_enabled=sound_enabled
            )
        except KDSInstanceNotFound as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)
        except KDSError as exc:
            return Response({"detail": str(exc), "field": "density"}, status=status.HTTP_400_BAD_REQUEST)
        from shopman.backstage.projections.kds import station_density

        return Response({"density": station_density(instance), "sound_enabled": bool(instance.sound_enabled)})


@extend_schema_view(
    post=extend_schema(
        tags=["backstage"],
        summary="Levar a estação no bolso: o pedido novo chega por push",
        responses={200: OpenApiResponse(description="Operador segue a estação.")},
    ),
)
class KDSStationFollowView(APIView):
    permission_classes = [HasBackstagePermission]
    required_permission = "backstage.operate_kds"

    def post(self, request, ref: str):
        try:
            kds_service.follow_station(station_ref=ref, user=request.user)
        except KDSInstanceNotFound as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)
        return Response({"ok": True})


@extend_schema_view(
    post=extend_schema(
        tags=["backstage"],
        summary="Start KDS ticket (put it in progress)",
        responses={200: OpenApiResponse(description="Updated ticket projection.")},
    ),
)
class KDSTicketStartView(APIView):
    permission_classes = [HasBackstagePermission]
    required_permission = "backstage.operate_kds"

    def post(self, request, ticket_pk: int):
        try:
            kds_service.start_ticket(ticket_pk=ticket_pk, actor=_actor(request))
        except KDSTicketNotFound as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)
        except KDSError as exc:
            logger.debug("kds_ticket_start_failed ticket_pk=%s", ticket_pk, exc_info=True)
            return Response({"detail": str(exc) or "Falha ao iniciar o preparo."}, status=status.HTTP_400_BAD_REQUEST)
        ticket = build_kds_ticket(ticket_pk)
        return Response({"ticket": projection_data(ticket)})


@extend_schema_view(
    post=extend_schema(
        tags=["backstage"],
        summary="Mark KDS ticket as done",
        responses={200: OpenApiResponse(description="Ticket completion result.")},
    ),
)
class KDSTicketDoneView(APIView):
    permission_classes = [HasBackstagePermission]
    required_permission = "backstage.operate_kds"

    def post(self, request, ticket_pk: int):
        try:
            kds_service.mark_ticket_done(ticket_pk=ticket_pk, actor=_actor(request))
        except KDSTicketNotFound as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)
        except KDSError as exc:
            logger.debug("kds_ticket_done_failed ticket_pk=%s", ticket_pk, exc_info=True)
            return Response({"detail": str(exc) or "Falha ao marcar como pronto."}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"ok": True, "ticket_pk": ticket_pk})


@extend_schema_view(
    post=extend_schema(
        tags=["backstage"],
        summary="Recall (reopen) a done KDS ticket",
        responses={200: OpenApiResponse(description="Ticket reopened.")},
    ),
)
class KDSTicketRecallView(APIView):
    # A estação reabre o próprio ticket; o Gestor devolve à cozinha pelo menu do
    # pedido pronto (SUITE-UX §15: a Saída mora no Gestor). Mesma régua de
    # servidor (``kds.recall_block_reason``) nas duas portas.
    permission_classes = [HasAnyBackstagePermission]
    any_permission = ("backstage.operate_kds", "shop.manage_orders")

    def post(self, request, ticket_pk: int):
        try:
            kds_service.recall_ticket(ticket_pk=ticket_pk, actor=_actor(request))
        except KDSTicketNotFound as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)
        except KDSError as exc:
            logger.debug("kds_ticket_recall_failed ticket_pk=%s", ticket_pk, exc_info=True)
            return Response({"detail": str(exc) or "Falha ao reabrir."}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"ok": True, "ticket_pk": ticket_pk})


@extend_schema_view(
    post=extend_schema(
        tags=["backstage"],
        summary="Acknowledge a cancelled KDS ticket (dismiss from board)",
        responses={200: OpenApiResponse(description="Ticket acknowledged.")},
    ),
)
class KDSTicketAcknowledgeView(APIView):
    permission_classes = [HasBackstagePermission]
    required_permission = "backstage.operate_kds"

    def post(self, request, ticket_pk: int):
        try:
            kds_service.acknowledge_ticket(ticket_pk=ticket_pk, actor=_actor(request))
        except KDSTicketNotFound as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)
        except KDSError as exc:
            logger.debug("kds_ticket_ack_failed ticket_pk=%s", ticket_pk, exc_info=True)
            return Response({"detail": str(exc) or "Falha ao dar baixa."}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"ok": True, "ticket_pk": ticket_pk})


@extend_schema_view(
    post=extend_schema(
        tags=["backstage"],
        summary="Acknowledge the changes shown on a live KDS ticket (Visto)",
        responses={200: OpenApiResponse(description="Changes acknowledged.")},
    ),
)
class KDSTicketChangesSeenView(APIView):
    """O Visto da mudança no card vivo: dá baixa nos cancelados que ele resumia."""

    permission_classes = [HasBackstagePermission]
    required_permission = "backstage.operate_kds"

    def post(self, request, ticket_pk: int):
        body = request.data if isinstance(request.data, dict) else {}
        cancelled_pks = body.get("cancelled_pks") or []
        if not isinstance(cancelled_pks, list):
            return Response(
                {"detail": "Lista de cancelados inválida.", "field": "cancelled_pks"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            result = kds_service.acknowledge_changes(
                ticket_pk=ticket_pk,
                cancelled_pks=cancelled_pks,
                seen_ref=str(body.get("seen_ref") or ""),
                actor=_actor(request),
            )
        except KDSTicketNotFound as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)
        except KDSError as exc:
            logger.debug("kds_ticket_changes_seen_failed ticket_pk=%s", ticket_pk, exc_info=True)
            return Response({"detail": str(exc) or "Falha ao registrar o Visto."}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"ok": True, "ticket_pk": ticket_pk, **result})


#: Quem pode dar o "Pronto" da estação sem tela: a Saída (KDS) e o PDV. O
#: grupo Caixa tem ``operate_pos`` e não ``operate_kds`` — e o balcão é uma das
#: três portas da baixa (decisão do dono, 26/09/2026).
PRINTED_STATION_PERMISSIONS = ("backstage.operate_kds", "cashman.operate_pos")

#: O "Pronto" da estação sem tela POR PEDIDO, que a Saída dava e agora o cartão
#: do Gestor dá (SUITE-UX §15: a Saída mora no Gestor). Quem gerencia pedidos
#: entra junto de quem expede e de quem opera o balcão.
EXIT_STATION_PERMISSIONS = (*PRINTED_STATION_PERMISSIONS, "shop.manage_orders")


@extend_schema_view(
    post=extend_schema(
        tags=["backstage"],
        summary="Saída: a estação sem tela terminou a parte dela neste pedido",
        responses={
            200: OpenApiResponse(description="Tickets concluídos."),
            400: OpenApiResponse(description="Estação com tela, ticket cancelado ou pedido travado."),
            404: OpenApiResponse(description="Pedido ou estação inexistente."),
        },
    ),
)
class KDSExitPrintedStationDoneView(APIView):
    permission_classes = [HasAnyBackstagePermission]
    any_permission = EXIT_STATION_PERMISSIONS

    def post(self, request, order_pk: int, station_ref: str):
        try:
            completed = kds_service.mark_printed_station_done_for_order(
                order_id=order_pk,
                station_ref=station_ref,
                actor=_actor(request),
            )
        except (KDSOrderNotFound, KDSInstanceNotFound) as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)
        except KDSError as exc:
            logger.debug(
                "kds_exit_printed_station_done_failed order_pk=%s station=%s", order_pk, station_ref, exc_info=True
            )
            return Response({"detail": str(exc) or "Falha ao marcar como pronto."}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"ok": True, "order_pk": order_pk, "station_ref": station_ref, "completed": completed})


@extend_schema_view(
    post=extend_schema(
        tags=["backstage"],
        summary="PDV: pronto no ticket de uma estação sem tela",
        responses={
            200: OpenApiResponse(description="O ticket, como o aviso do balcão o diz."),
            400: OpenApiResponse(description="Estação com tela, ticket cancelado ou pedido travado."),
            404: OpenApiResponse(description="Ticket inexistente."),
        },
    ),
)
class KDSPrintedTicketDoneView(APIView):
    permission_classes = [HasAnyBackstagePermission]
    any_permission = PRINTED_STATION_PERMISSIONS

    def post(self, request, ticket_pk: int):
        from shopman.backstage.models import KDSTicket

        try:
            ticket, completed = kds_service.mark_printed_ticket_done(
                ticket_pk=ticket_pk,
                actor=_actor(request),
                via=KDSTicket.COMPLETED_VIA_POS,
            )
        except KDSTicketNotFound as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)
        except KDSError as exc:
            logger.debug("kds_printed_ticket_done_failed ticket_pk=%s", ticket_pk, exc_info=True)
            return Response({"detail": str(exc) or "Falha ao marcar como pronto."}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"ticket": projection_data(build_printed_ticket_receipt(ticket, completed_now=completed))})


@extend_schema_view(
    post=extend_schema(
        tags=["backstage"],
        summary="Leitor de código: pronto no ticket do QR da Via Cozinha",
        responses={
            200: OpenApiResponse(description="O ticket, como o aviso do balcão o diz."),
            400: OpenApiResponse(description="Ticket cancelado ou pedido travado."),
            404: OpenApiResponse(description="Código que não é de uma Via Cozinha desta loja."),
        },
    ),
)
class KDSPrintedTicketScanView(APIView):
    permission_classes = [HasAnyBackstagePermission]
    any_permission = PRINTED_STATION_PERMISSIONS

    def post(self, request):
        code = str(request.data.get("code") or "").strip()
        if not code:
            return Response({"detail": "Leia o código da Via Cozinha."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            ticket, completed = kds_service.mark_scanned_ticket_done(code=code, actor=_actor(request))
        except KDSTicketNotFound as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)
        except KDSError as exc:
            logger.debug("kds_printed_ticket_scan_failed", exc_info=True)
            return Response({"detail": str(exc) or "Falha ao marcar como pronto."}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"ticket": projection_data(build_printed_ticket_receipt(ticket, completed_now=completed))})


@extend_schema_view(
    get=extend_schema(
        tags=["backstage"],
        summary="Customer pickup board (public)",
        responses={200: OpenApiResponse(description="Customer status projection.")},
    ),
)
class KDSCustomerStatusView(APIView):
    """Public read-only endpoint for the pickup display."""

    permission_classes = []

    def get(self, request):
        try:
            limit = int(request.query_params.get("limit", 24))
        except (TypeError, ValueError):
            return Response({"detail": "Parâmetro limit inválido."}, status=status.HTTP_400_BAD_REQUEST)
        limit = max(1, min(limit, 100))
        status_proj = build_kds_customer_status(limit=limit)
        return Response({"status": projection_data(status_proj)})
