"""
Backstage Campaign API — o painel de revisão do marketing operacional.

Contrato consumido por `surfaces/marketing-nuxt` (:3006). Read = projections de
`backstage.projections.campaign`; write = aprovar/recusar/editar announcement e CRUD
de regras e modelos. Cada operação exige sua capability; a permissão ampla
legada só mantém leitura/edição/preview durante a migração.

    GET    campaign/                    → painel (pendentes, recentes, placar)
    GET    campaign/history/            → tudo que já saiu
    GET    campaign/options/            → vocabulário do formulário de regra
    GET    campaign/platforms/          → estado de entrega de cada plataforma
    POST   campaign/preview/            → como a mensagem vai ficar (mesmo resolvedor do envio)
    GET    campaign/announcements/<pk>/         → um announcement
    PATCH  campaign/announcements/<pk>/         → editar antes de aprovar
    POST   campaign/announcements/<pk>/approve/ → publicar
    POST   campaign/announcements/<pk>/reject/ → recusar (com motivo)
    GET    campaign/announcements/<pk>/delivery-actions/ → recovery Actions
    POST   campaign/announcements/<pk>/retry-deliveries/ → repetir falhas seguras
    POST   campaign/announcements/<pk>/reconcile-deliveries/ → consultar unknown
    POST   campaign/announcements/<pk>/rewrite/ → sugestão de corpo pela IA
    POST   campaign/rules/<pk>/fire/    → disparar AGORA (público opcional)
    GET    campaign/whatsapp-template/  → templates aprovados + o escolhido
    POST   campaign/whatsapp-template/  → escolher o template
    POST   campaign/whatsapp-template/test/ → mandar UM teste para UM número
    GET    campaign/rules/              → listar         POST → criar
    PATCH  campaign/rules/<pk>/         → editar         DELETE → apagar
    GET    campaign/templates/          → listar         POST → criar
    PATCH  campaign/templates/<pk>/     → editar         DELETE → apagar

Toda decisão de publicação delega a ``shopman.shop.services.campaign``: a API
não reimplementa o despacho por plataforma nem a régua de expiração.
"""

from __future__ import annotations

import logging

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.db.models import ProtectedError, Q
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema, extend_schema_view
from rest_framework.exceptions import AuthenticationFailed, NotAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from shopman.backstage.api.marketing_cursor import (
    InvalidMarketingCursor,
    MarketingCursor,
    decode_cursor,
    encode_cursor,
    first_cursor,
)
from shopman.backstage.api.marketing_v2_http import (
    MarketingV2Problem,
    marketing_v2_response,
    response_for_exception,
)
from shopman.backstage.api.permissions import HasMarketingCapability
from shopman.backstage.api.projections import projection_data
from shopman.backstage.api.throttles import (
    MarketingAIThrottle,
    MarketingAudienceShopThrottle,
    MarketingAudienceUserThrottle,
    MarketingDangerousShopThrottle,
    MarketingDangerousUserThrottle,
    MarketingFireShopThrottle,
    MarketingFireUserThrottle,
)
from shopman.backstage.projections import marketing as marketing_projection
from shopman.backstage.projections import marketing_v2 as marketing_projection_v2
from shopman.backstage.projections.marketing_actions import (
    CampaignActionContext,
    PlatformActionContext,
    resolve_actions,
    resolve_actions_for,
    with_resolved_actions,
)
from shopman.shop.models import Announcement, AnnouncementStatus, AnnouncementTemplate, Campaign, Trigger
from shopman.shop.services import campaign as campaign_service
from shopman.shop.services.marketing_commands import (
    MarketingCommandConflict,
    MarketingCommandRejected,
)
from shopman.shop.services.marketing_contracts import MarketingContractError
from shopman.shop.services.marketing_observability import observe_projection
from shopman.shop.services.marketing_security import (
    MarketingAuthorizationError,
    MarketingAuthorizationRequired,
)

logger = logging.getLogger(__name__)

_HISTORY_DEFAULT_LIMIT = 100
_HISTORY_MAX_LIMIT = 300
_HISTORY_V2_DEFAULT_LIMIT = 50
_HISTORY_V2_MAX_LIMIT = 100
_HISTORY_V2_COLLECTION = "marketing-history"

#: Plataformas aceitas numa regra — mesma lista que a tela oferece.
_VALID_PLATFORMS = {ref for ref, _ in marketing_projection.PLATFORM_CHOICES}
_AUTHORIZATION_FIELDS = frozenset({"confirmation_token", "typed_confirmation"})
_DANGEROUS_THROTTLES = (
    MarketingDangerousUserThrottle,
    MarketingDangerousShopThrottle,
)


class _CampaignBase(APIView):
    permission_classes = [HasMarketingCapability]
    permission_map = {"GET": "shop.view_marketing"}

    def get_required_permissions(self, request):
        return self.permission_map.get(request.method, ())

    def handle_exception(self, exc):
        # SessionAuthentication não fornece `WWW-Authenticate`; o DRF converteria
        # NotAuthenticated em 403. Para o cockpit isso apaga a diferença entre
        # sessão ausente/expirada (reauth resolve) e capability negada (reauth não
        # resolve), portanto o dialeto legado também fixa 401 explicitamente.
        if isinstance(exc, (NotAuthenticated, AuthenticationFailed)):
            return Response(
                {"detail": "Autenticação necessária.", "code": "not_authenticated"},
                status=401,
            )
        return super().handle_exception(exc)


class _CampaignV2Base(_CampaignBase):
    """Apply the strict error dialect before DRF can collapse 401 into 403."""

    def handle_exception(self, exc):
        response = response_for_exception(self.request, exc)
        return response if response is not None else super().handle_exception(exc)


class MarketingStepUpView(_CampaignBase):
    """Establish password/TOTP freshness for a later exact confirmation."""

    permission_map = {"POST": "shop.view_marketing"}
    throttle_classes = list(_DANGEROUS_THROTTLES)

    def post(self, request):
        from django.contrib.auth import get_user_model
        from django_otp.plugins.otp_totp.models import TOTPDevice

        from shopman.shop.services.marketing_security import record_step_up

        payload = request.data if isinstance(request.data, dict) else {}
        unexpected = sorted(set(payload) - {"method", "credential"})
        if unexpected:
            return _unknown_command_fields(unexpected)
        method = str(payload.get("method") or "").strip()
        credential = str(payload.get("credential") or "").strip().replace(" ", "")
        actor = get_user_model().objects.filter(pk=request.user.pk, is_active=True).first()
        verified = False
        if actor is not None and method == "password":
            verified = actor.check_password(credential)
        elif actor is not None and method == "totp":
            verified = bool(
                credential
                and any(
                    device.verify_token(credential) for device in TOTPDevice.objects.filter(user=actor, confirmed=True)
                )
            )
        if not verified:
            return Response(
                {
                    "code": "step_up_failed",
                    "detail": "A confirmação de identidade não conferiu.",
                    "field_errors": {"credential": ["Tente novamente."]},
                },
                status=403,
            )
        return Response({"ok": True, "step_up": record_step_up(request, level=method)})


class MarketingDualControlView(_CampaignBase):
    """Let a distinct authorized person approve one exact open token."""

    permission_map = {"POST": "shop.view_marketing"}
    throttle_classes = list(_DANGEROUS_THROTTLES)

    def post(self, request):
        from shopman.shop.services.marketing_security import (
            approve_second_actor,
            step_up_evidence_from_session,
        )

        payload = request.data if isinstance(request.data, dict) else {}
        unexpected = sorted(set(payload) - {"confirmation_token"})
        if unexpected:
            return _unknown_command_fields(unexpected)
        try:
            confirmation = approve_second_actor(
                str(payload.get("confirmation_token") or ""),
                actor=request.user,
                step_up=step_up_evidence_from_session(request),
            )
        except (MarketingAuthorizationRequired, MarketingAuthorizationError) as exc:
            return _authorization_error_response(exc, request)
        return Response(
            {
                "ok": True,
                "confirmation_ref": str(confirmation.ref),
                "second_control": "approved",
                "expires_at": confirmation.expires_at.isoformat(),
            }
        )


class MarketingFreezeView(_CampaignBase):
    """Read or immediately activate the persisted Marketing kill switch."""

    permission_map = {
        "GET": "shop.view_marketing",
        "POST": "shop.freeze_marketing",
    }

    def get(self, request):
        from shopman.shop.services.marketing_security import safety_state

        state = safety_state()
        return Response(_safety_payload(state))

    def post(self, request):
        from shopman.shop.services.marketing_security import activate_freeze

        payload = request.data if isinstance(request.data, dict) else {}
        unexpected = sorted(set(payload) - {"reason"})
        if unexpected:
            return _unknown_command_fields(unexpected)
        try:
            state = activate_freeze(actor=request.user, reason=payload.get("reason", ""))
        except (MarketingAuthorizationRequired, MarketingAuthorizationError) as exc:
            return _authorization_error_response(exc, request)
        return Response({"ok": True, **_safety_payload(state)})


class MarketingUnfreezeView(_CampaignBase):
    """Resume only after CAS, reconciliation, TOTP and distinct second control."""

    permission_map = {"POST": "shop.freeze_marketing"}
    throttle_classes = list(_DANGEROUS_THROTTLES)

    def post(self, request):
        from shopman.shop.services.marketing_security import (
            deactivate_freeze,
            step_up_evidence_from_session,
        )

        payload = request.data if isinstance(request.data, dict) else {}
        unexpected = sorted(set(payload) - {"base_version", "confirmation_token"})
        if unexpected:
            return _unknown_command_fields(unexpected)
        base_version, error = _command_version(payload)
        if error:
            return error
        try:
            state = deactivate_freeze(
                actor=request.user,
                base_version=base_version,
                token=str(payload.get("confirmation_token") or ""),
                step_up=step_up_evidence_from_session(request),
            )
        except (MarketingAuthorizationRequired, MarketingAuthorizationError) as exc:
            return _authorization_error_response(exc, request)
        return Response({"ok": True, **_safety_payload(state)})


# ── Leitura ──────────────────────────────────────────────────────────


@extend_schema_view(
    get=extend_schema(
        tags=["backstage"],
        summary="Campaign board — pending announcements, recent announcements, day stats",
        responses={200: OpenApiResponse(description="Painel do gestor de campanhas.")},
    ),
)
class CampaignBoardView(_CampaignBase):
    def get(self, request):
        board = marketing_projection.build_board()
        return Response({"board": projection_data(board)})


@extend_schema_view(
    get=extend_schema(
        tags=["backstage"],
        summary="Canonical Marketing v2 board facts",
        responses={200: OpenApiResponse(description="Marketing v2 projection envelope.")},
    ),
)
class CampaignBoardV2View(_CampaignV2Base):
    """Additive read contract; the v1 board remains available during cutover."""

    def get(self, request):
        envelope = observe_projection(
            "board",
            lambda: with_resolved_actions(
                marketing_projection_v2.build_board(),
                actor=request.user,
            ),
        )
        return marketing_v2_response(request, envelope)


class AnnouncementDetailV2View(_CampaignV2Base):
    """One canonical v2 announcement projection, without audience membership."""

    def get(self, request, pk: int):
        def build_detail():
            announcement = _announcement_or_none(pk)
            if announcement is None:
                raise MarketingV2Problem(
                    status_code=404,
                    code="resource_not_found",
                    detail="presentation.resource_not_found",
                )
            return with_resolved_actions(
                marketing_projection_v2.build_announcement(announcement),
                actor=request.user,
            )

        envelope = observe_projection(
            "detail",
            build_detail,
        )
        return marketing_v2_response(request, envelope)


class CampaignHistoryV2View(_CampaignV2Base):
    """A stable, opaque-cursor history page pinned to its first ``as_of``."""

    def get(self, request):
        from shopman.backstage.marketing_history import (
            InvalidHistoryFilter,
            apply_history_filters,
            cursor_collection,
            parse_history_filters,
        )

        limit = _history_v2_limit(request)
        try:
            filters = parse_history_filters(request.query_params)
        except InvalidHistoryFilter as exc:
            raise MarketingV2Problem(
                status_code=422,
                code=f"invalid_{exc.field}",
                detail="presentation.invalid_filter",
                field_errors={exc.field: ("presentation.invalid_filter",)},
            ) from exc
        collection = cursor_collection(_HISTORY_V2_COLLECTION, filters)
        raw_cursor = str(request.query_params.get("cursor") or "").strip()
        try:
            cursor = (
                decode_cursor(raw_cursor, collection=collection)
                if raw_cursor
                else first_cursor(collection=collection)
            )
        except InvalidMarketingCursor as exc:
            raise MarketingV2Problem(
                status_code=422,
                code="invalid_cursor",
                detail="presentation.invalid_cursor",
                field_errors={"cursor": ("presentation.invalid_cursor",)},
            ) from exc

        queryset = (
            Announcement.objects.filter(
                status__in=marketing_projection.RESULT_VISIBLE_STATUSES,
                created_at__lte=cursor.as_of,
            )
            .select_related("rule", "template")
            .order_by("-created_at", "-pk")
        )
        queryset = apply_history_filters(queryset, filters, as_of=cursor.as_of)
        if cursor.created_at is not None and cursor.pk is not None:
            queryset = queryset.filter(
                Q(created_at__lt=cursor.created_at) | Q(created_at=cursor.created_at, pk__lt=cursor.pk)
            )

        def build_history():
            rows = list(queryset[: limit + 1])
            has_more = len(rows) > limit
            page_rows = rows[:limit]
            next_cursor = ""
            if has_more:
                last = page_rows[-1]
                next_cursor = encode_cursor(
                    MarketingCursor(
                        collection=collection,
                        as_of=cursor.as_of,
                        created_at=last.created_at,
                        pk=last.pk,
                    )
                )
            return with_resolved_actions(
                marketing_projection_v2.build_history_page(
                    page_rows,
                    as_of=cursor.as_of,
                    limit=limit,
                    has_more=has_more,
                    next_cursor=next_cursor,
                ),
                actor=request.user,
                now=cursor.as_of,
            )

        envelope = observe_projection(
            "history",
            build_history,
        )
        return marketing_v2_response(request, envelope)


@extend_schema_view(
    get=extend_schema(
        tags=["backstage"],
        summary="Campaign history — everything that went out",
        parameters=[OpenApiParameter("limit", int, description="Máximo de itens (default 100).")],
        responses={200: OpenApiResponse(description="Posts publicados, do mais recente.")},
    ),
)
class CampaignHistoryView(_CampaignBase):
    def get(self, request):
        announcements = marketing_projection.build_history(limit=_limit(request))
        return Response({"announcements": projection_data(announcements)})


@extend_schema_view(
    get=extend_schema(
        tags=["backstage"],
        summary="Vocabulary for the rule form (triggers, platforms, templates, variables)",
        responses={200: OpenApiResponse(description="Opções do formulário de regra.")},
    ),
)
class CampaignOptionsView(_CampaignBase):
    def get(self, request):
        return Response({"options": projection_data(marketing_projection.build_options())})


# ── Posts ────────────────────────────────────────────────────────────


class AnnouncementDetailView(_CampaignBase):
    """Ler um announcement, ou editá-lo antes de aprovar.

    A edição é a razão de a revisão existir: a IA (ou o template) escreveu, o
    gestor ajusta o tom e só então publica. Anúncio já despachado não se edita —
    reescrever o que o cliente já leu seria mentira retroativa.
    """

    permission_map = {
        "GET": "shop.view_marketing",
        "PATCH": "shop.edit_marketing_campaigns",
    }

    def get(self, request, pk: int):
        announcement = _announcement_or_none(pk)
        if announcement is None:
            return Response({"detail": "Anúncio não encontrado."}, status=404)
        from shopman.shop.services.marketing_time import (
            configured_timezone_name,
            quiet_hours_suspended_for_local_simulation,
        )

        return Response(
            {
                "announcement": projection_data(marketing_projection.build_announcement(announcement)),
                "shop_timezone": configured_timezone_name(),
                "quiet_hours_suspended_for_local_simulation": (
                    quiet_hours_suspended_for_local_simulation()
                ),
            }
        )

    def patch(self, request, pk: int):
        announcement = _announcement_or_none(pk)
        if announcement is None:
            return Response({"detail": "Anúncio não encontrado."}, status=404)
        if announcement.status not in (AnnouncementStatus.DRAFT, AnnouncementStatus.PENDING_REVIEW):
            return Response(
                {"detail": "Este anúncio já saiu. Não dá para reescrever o que já foi lido."},
                status=400,
            )

        edits, error = _announcement_edits(request.data)
        if error:
            return Response(error, status=400)
        if not edits:
            return Response({"detail": "Nada para salvar."}, status=400)

        base_version = None
        if "base_version" in request.data:
            raw_base_version = request.data.get("base_version")
            base_version = None if isinstance(raw_base_version, bool) else _as_int(raw_base_version)
            if base_version is None or base_version <= 0:
                return Response(
                    {
                        "detail": "A versão deve ser um inteiro positivo.",
                        "field": "base_version",
                    },
                    status=422,
                )

        # Pelo serviço, não direto no model: ele renderiza novamente as
        # variantes explícitas sem substituir seu conteúdo pelo corpo comum.
        try:
            announcement = campaign_service.update_content(
                pk,
                base_version=base_version,
                **edits,
            )
        except campaign_service.CampaignVersionConflict as exc:
            return Response(
                {
                    "code": "version_conflict",
                    "detail": str(exc),
                    "current_version": exc.current_version,
                    "field_errors": {"base_version": ["Use a versão atual."]},
                },
                status=409,
            )
        except MarketingContractError as exc:
            return _command_error_response(exc)
        except campaign_service.CampaignError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response(
            {"ok": True, "announcement": projection_data(marketing_projection.build_announcement(announcement))}
        )


class AnnouncementApproveView(_CampaignBase):
    """Publicar — agora ou na hora marcada.

    O comando v2 cria uma outbox durável por lane; o consumer só a entrega à
    fila depois do commit. As edições do card vão no MESMO request: salvar e
    aprovar em duas chamadas abriria a janela para publicar a versão anterior.
    """

    permission_map = {
        "POST": (
            "shop.approve_marketing_announcements",
            "shop.publish_marketing_announcements",
        ),
    }
    throttle_classes = list(_DANGEROUS_THROTTLES)

    def post(self, request, pk: int):
        # Additive v2 migration: a caller that declares version/publish_mode is a
        # command caller and can never fall through to the non-idempotent legacy
        # path. Old clients remain readable until the cutover task removes it.
        if _is_approval_command(request):
            return self._post_command(request, pk)
        return _command_protocol_required()

    def _post_command(self, request, pk: int):
        from shopman.shop.services import marketing_approval
        from shopman.shop.services.marketing_commands import (
            MarketingCommandConflict,
            MarketingCommandRejected,
        )
        from shopman.shop.services.marketing_contracts import MarketingContractError

        payload = request.data if isinstance(request.data, dict) else {}
        allowed = {
            "base_version",
            "body",
            "hashtags",
            "image_url",
            "platforms",
            "publish_at",
            "publish_mode",
            "publish_timezone",
            "ai_suggestion_ref",
        } | _AUTHORIZATION_FIELDS
        unexpected = sorted(set(payload) - allowed)
        if unexpected:
            return Response(
                {
                    "code": "unknown_command_fields",
                    "detail": "A aprovação contém campos desconhecidos.",
                    "field_errors": {"payload": unexpected},
                },
                status=422,
            )

        raw_version = payload.get("base_version")
        base_version = None if isinstance(raw_version, bool) else _as_int(raw_version)
        if base_version is None or base_version <= 0:
            return Response(
                {
                    "code": "invalid_base_version",
                    "detail": "Informe a versão exibida na revisão.",
                    "field_errors": {"base_version": ["Use um inteiro positivo."]},
                },
                status=422,
            )
        publish_mode = str(payload.get("publish_mode") or "").strip()
        publish_timezone = str(payload.get("publish_timezone") or "").strip()
        publish_at, error = _publish_at(
            payload.get("publish_at"),
            timezone_name=publish_timezone,
        )
        if error:
            field = str(error.get("field") or "publish_at")
            return Response(
                {
                    "code": str(error.get("code") or "invalid_publish_at"),
                    "detail": error["detail"],
                    "field_errors": {field: [error["detail"]]},
                },
                status=422,
            )
        edits, error = _announcement_edits(payload)
        if error:
            field = str(error.get("field") or "payload")
            return Response(
                {
                    "code": "invalid_approval_content",
                    "detail": error["detail"],
                    "field_errors": {field: [error["detail"]]},
                },
                status=422,
            )

        announcement = _announcement_or_none(pk)
        if announcement is None:
            # The service still creates a replayable rejected receipt. Empty
            # placeholder content never reaches an operation because the resource
            # lookup in the command boundary wins first.
            content = {"body": "resource-not-found"}
            platform_content = {}
            platforms = ["instagram"]
        else:
            content = dict(announcement.content or {})
            if "body" in edits:
                content["body"] = edits["body"]
            if "hashtags" in edits:
                content["hashtags"] = edits["hashtags"]
            if "image_url" in edits:
                content["image_url"] = edits["image_url"]
            platforms = edits.get("platforms", list(announcement.platforms or []))
            platform_content = (
                campaign_service._platform_content(
                    announcement.template,
                    content,
                    platforms=platforms,
                )
                if announcement.template_id
                else dict(announcement.platform_content or {})
            )

        try:
            result = marketing_approval.approve_command(
                pk,
                actor=request.user,
                idempotency_key=str(request.headers.get("Idempotency-Key") or ""),
                base_version=base_version,
                publish_mode=publish_mode,
                publish_at=publish_at,
                publish_timezone=publish_timezone,
                content=content,
                platform_content=platform_content,
                platforms=platforms,
                request_id=str(request.headers.get("X-Request-ID") or ""),
                ai_suggestion_ref=str(payload.get("ai_suggestion_ref") or "").strip(),
                # Fingerprint only the normalized client intention. Server-side
                # enrichment may change after a conflict, but replaying the same
                # HTTP command must still retrieve its original receipt.
                idempotency_payload={
                    "edits": edits,
                    "ai_suggestion_ref": str(payload.get("ai_suggestion_ref") or "").strip(),
                    "publish_at": publish_at.isoformat() if publish_at else "",
                    "publish_mode": publish_mode,
                    "publish_timezone": publish_timezone,
                },
                authorization=_command_authorizer(
                    request,
                    capability="shop.publish_marketing_announcements",
                    additional_capabilities=("shop.approve_marketing_announcements",),
                ),
            )
        except (MarketingAuthorizationRequired, MarketingAuthorizationError) as exc:
            return _authorization_error_response(exc, request)
        except (
            MarketingCommandConflict,
            MarketingCommandRejected,
            MarketingContractError,
        ) as exc:
            return _command_error_response(exc)

        receipt = result.receipt
        logger.info(
            "campaign.approval_command actor=%s announcement=%s receipt=%s replayed=%s",
            request.user.pk,
            pk,
            receipt.ref,
            result.replayed,
        )
        return Response(
            {
                "ok": True,
                "scheduled": receipt.outcome.get("publish_mode") == "scheduled",
                "replayed": result.replayed,
                "receipt": {
                    "ref": str(receipt.ref),
                    "kind": receipt.kind,
                    "state": receipt.state,
                    "base_version": receipt.base_version,
                    "resulting_version": receipt.resulting_version,
                    "resource_ref": receipt.resource_ref,
                    "outcome": receipt.outcome,
                    "created_at": receipt.created_at.isoformat(),
                    "completed_at": (receipt.completed_at.isoformat() if receipt.completed_at else ""),
                },
                "announcement": projection_data(marketing_projection.build_announcement(result.announcement)),
            }
        )


class WhatsAppTestSendView(_CampaignBase):
    """POST campaign/whatsapp-template/test/ → teste sandbox unitário.

    Fica ao lado da escolha do template porque é a mesma pergunta: "isto renderiza como eu
    escrevi?". Mandar o gestor abrir um terminal para descobrir seria transformar uma
    conferência de dez segundos em tarefa de infraestrutura.

    O operador escolhe uma ref allowlisted; telefone/subscriber não entra no payload,
    resposta ou log. A lane é separada de audiência e deixa receipt idempotente.
    """

    permission_map = {"POST": "shop.send_marketing_test"}
    throttle_classes = list(_DANGEROUS_THROTTLES)

    def post(self, request):
        payload = request.data if isinstance(request.data, dict) else {}
        unexpected = sorted(set(payload) - {"target_ref", "sku", "body"})
        if unexpected:
            return Response(
                {
                    "detail": "O teste aceita apenas destino verificado, SKU e texto.",
                    "code": "test_payload_not_isolated",
                    "fields": unexpected,
                },
                status=422,
            )
        try:
            outcome = campaign_service.send_test(
                str(payload.get("target_ref") or ""),
                actor=request.user,
                idempotency_key=str(request.headers.get("Idempotency-Key") or ""),
                sku=str(payload.get("sku") or ""),
                body=str(payload.get("body") or ""),
            )
        except campaign_service.MarketingTestConflict as exc:
            return Response({"detail": str(exc), "code": "idempotency_conflict"}, status=409)
        except campaign_service.MarketingTestThrottled as exc:
            return Response(
                {"detail": str(exc), "code": "test_send_throttled"},
                status=429,
                headers={"Retry-After": str(exc.retry_after)},
            )
        except campaign_service.MarketingTestUnavailable as exc:
            return Response(
                {
                    "detail": str(exc),
                    "code": "sandbox_unavailable",
                    "receipt_ref": exc.receipt_ref,
                },
                status=503,
            )
        except campaign_service.MarketingTestForbidden as exc:
            return Response(
                {
                    "detail": str(exc),
                    "code": "capability_revoked",
                    "receipt_ref": exc.receipt_ref,
                },
                status=403,
            )
        except campaign_service.CampaignError as exc:
            return Response({"detail": str(exc), "code": "invalid_test_send"}, status=422)

        logger.info(
            "campaign.test_send_api actor=%s receipt=%s state=%s replayed=%s",
            request.user.pk,
            outcome.receipt_ref,
            outcome.state,
            outcome.replayed,
        )
        return Response(
            {
                "ok": outcome.accepted,
                "backend": outcome.backend,
                "target_ref": outcome.target_ref,
                "fields": outcome.fields,
                "receipt_ref": outcome.receipt_ref,
                "state": outcome.state,
                "sandbox": outcome.sandbox,
                "max_targets": outcome.max_targets,
                "replayed": outcome.replayed,
                "detail": outcome.detail,
            }
        )


class AnnouncementRewriteView(_CampaignBase):
    """Return a validated, content-addressed suggestion; never mutate the draft."""

    permission_map = {"POST": "shop.approve_marketing_announcements"}
    throttle_classes = [MarketingAIThrottle]

    def post(self, request, pk: int):
        from shopman.shop.services import marketing_ai

        payload = request.data if isinstance(request.data, dict) else {}
        unexpected = sorted(set(payload) - {"body"})
        if unexpected:
            return Response(
                {
                    "code": "unknown_suggestion_fields",
                    "detail": "O pedido de sugestão contém campos desconhecidos.",
                    "field_errors": {"payload": unexpected},
                },
                status=422,
            )
        try:
            suggestion = marketing_ai.suggest(
                pk,
                actor=request.user,
                current_body=str(payload.get("body") or ""),
                request_id=str(request.headers.get("X-Request-ID") or ""),
            )
        except marketing_ai.MarketingAIError as exc:
            return Response(exc.as_payload(), status=exc.status_code)

        return Response({"suggestion": suggestion.as_payload()})


class AnnouncementSuggestionDispositionView(_CampaignBase):
    """Record accept/discard telemetry; neither action persists announcement copy."""

    permission_map = {"POST": "shop.approve_marketing_announcements"}

    def post(self, request, pk: int, ref):
        from shopman.shop.models import MarketingAISuggestion
        from shopman.shop.services import marketing_ai

        payload = request.data if isinstance(request.data, dict) else {}
        if set(payload) != {"action"}:
            return Response(
                {"code": "ai_disposition_invalid", "detail": "Escolha usar ou descartar."},
                status=422,
            )
        action = str(payload.get("action") or "")
        event_type = {
            "accept_draft": "draft_accepted",
            "discard": "discarded",
        }.get(action)
        if event_type is None:
            return Response(
                {"code": "ai_disposition_invalid", "detail": "Escolha usar ou descartar."},
                status=422,
            )
        try:
            suggestion = MarketingAISuggestion.objects.filter(ref=ref).first()
            if suggestion is None or suggestion.announcement_id != pk:
                raise marketing_ai.MarketingAIError(
                    code="ai_suggestion_not_found",
                    detail="Esta sugestão não pertence ao anúncio.",
                    status_code=404,
                )
            marketing_ai.record_disposition(ref=str(ref), actor=request.user, event_type=event_type)
        except marketing_ai.MarketingAIError as exc:
            return Response(exc.as_payload(), status=exc.status_code)

        return Response({"ok": True, "action": action})


class AnnouncementRejectView(_CampaignBase):
    """Recusar sem publicar: o gestor viu e disse não.

    O motivo é obrigatório e a decisão sempre usa o command versionado.
    """

    permission_map = {"POST": "shop.approve_marketing_announcements"}

    def post(self, request, pk: int):
        payload = request.data if isinstance(request.data, dict) else {}
        reason = str(payload.get("reason") or "").strip()

        if not (request.headers.get("Idempotency-Key") or "base_version" in payload):
            return _command_protocol_required()
        unexpected = sorted(set(payload) - {"base_version", "reason"})
        if unexpected:
            return _unknown_command_fields(unexpected)
        base_version, error = _command_version(payload)
        if error:
            return error
        try:
            from shopman.shop.services.marketing_transitions import reject_command

            result = reject_command(
                pk,
                actor=request.user,
                idempotency_key=str(request.headers.get("Idempotency-Key") or ""),
                base_version=base_version,
                reason=reason,
                request_id=str(request.headers.get("X-Request-ID") or ""),
            )
        except (
            MarketingCommandConflict,
            MarketingCommandRejected,
            MarketingContractError,
        ) as exc:
            return _command_error_response(exc)
        return Response(_command_response(result))


class AnnouncementCancelView(_CampaignBase):
    """Cancel every outbox lane only while none has started."""

    permission_map = {"POST": "shop.publish_marketing_announcements"}
    throttle_classes = list(_DANGEROUS_THROTTLES)

    def post(self, request, pk: int):
        payload = request.data if isinstance(request.data, dict) else {}
        unexpected = sorted(set(payload) - ({"base_version", "reason"} | _AUTHORIZATION_FIELDS))
        if unexpected:
            return _unknown_command_fields(unexpected)
        base_version, error = _command_version(payload)
        if error:
            return error
        try:
            from shopman.shop.services.marketing_transitions import cancel_command

            result = cancel_command(
                pk,
                actor=request.user,
                idempotency_key=str(request.headers.get("Idempotency-Key") or ""),
                base_version=base_version,
                reason=str(payload.get("reason") or ""),
                request_id=str(request.headers.get("X-Request-ID") or ""),
                authorization=_command_authorizer(
                    request,
                    capability="shop.publish_marketing_announcements",
                ),
            )
        except (MarketingAuthorizationRequired, MarketingAuthorizationError) as exc:
            return _authorization_error_response(exc, request)
        except (
            MarketingCommandConflict,
            MarketingCommandRejected,
            MarketingContractError,
        ) as exc:
            return _command_error_response(exc)
        return Response(_command_response(result))


class AnnouncementRescheduleView(_CampaignBase):
    """Move all pending lanes while preserving their relative wave delay."""

    permission_map = {"POST": "shop.publish_marketing_announcements"}
    throttle_classes = list(_DANGEROUS_THROTTLES)

    def post(self, request, pk: int):
        payload = request.data if isinstance(request.data, dict) else {}
        unexpected = sorted(set(payload) - ({"base_version", "publish_at", "publish_timezone"} | _AUTHORIZATION_FIELDS))
        if unexpected:
            return _unknown_command_fields(unexpected)
        base_version, error = _command_version(payload)
        if error:
            return error
        publish_timezone = str(payload.get("publish_timezone") or "").strip()
        publish_at, parse_error = _publish_at(
            payload.get("publish_at"),
            timezone_name=publish_timezone,
        )
        if parse_error or publish_at is None:
            detail = parse_error["detail"] if parse_error else "Escolha a nova data e hora."
            return Response(
                {
                    "code": str((parse_error or {}).get("code") or "invalid_publish_at"),
                    "detail": detail,
                    "field_errors": {str((parse_error or {}).get("field") or "publish_at"): [detail]},
                },
                status=422,
            )
        try:
            from shopman.shop.services.marketing_transitions import reschedule_command

            result = reschedule_command(
                pk,
                actor=request.user,
                idempotency_key=str(request.headers.get("Idempotency-Key") or ""),
                base_version=base_version,
                publish_at=publish_at,
                publish_timezone=publish_timezone,
                request_id=str(request.headers.get("X-Request-ID") or ""),
                authorization=_command_authorizer(
                    request,
                    capability="shop.publish_marketing_announcements",
                ),
            )
        except (MarketingAuthorizationRequired, MarketingAuthorizationError) as exc:
            return _authorization_error_response(exc, request)
        except (
            MarketingCommandConflict,
            MarketingCommandRejected,
            MarketingContractError,
        ) as exc:
            return _command_error_response(exc)
        return Response(_command_response(result))


class AnnouncementDeliveryActionsView(_CampaignBase):
    """Resolve recovery Actions with current authority and ledger state."""

    permission_map = {"GET": "shop.view_marketing"}

    def get(self, request, pk: int):
        announcement = _announcement_or_none(pk)
        if announcement is None:
            return Response({"detail": "Anúncio não encontrado."}, status=404)
        envelope = with_resolved_actions(
            marketing_projection_v2.build_announcement(announcement),
            actor=request.user,
        )
        actions = tuple(
            action
            for action in envelope.actions
            if action.kind
            in {
                "retry_failed_delivery",
                "reconcile_unknown_delivery",
            }
        )
        return Response(
            {
                "resource_ref": f"announcement:{announcement.pk}",
                "version": announcement.version,
                "actions": projection_data(actions),
            }
        )


class AnnouncementRetryDeliveriesView(_CampaignBase):
    """Queue only the currently retryable failures selected by platform."""

    permission_map = {"POST": "shop.retry_failed_marketing"}
    throttle_classes = list(_DANGEROUS_THROTTLES)

    def post(self, request, pk: int):
        payload = request.data if isinstance(request.data, dict) else {}
        unexpected = sorted(set(payload) - ({"base_version", "platforms"} | _AUTHORIZATION_FIELDS))
        if unexpected:
            return _unknown_command_fields(unexpected)
        base_version, error = _command_version(payload)
        if error:
            return error
        try:
            from shopman.shop.services.marketing_delivery_recovery import (
                retry_failed_command,
            )

            result = retry_failed_command(
                pk,
                actor=request.user,
                idempotency_key=str(request.headers.get("Idempotency-Key") or ""),
                base_version=base_version,
                platforms=payload.get("platforms", ()),
                request_id=str(request.headers.get("X-Request-ID") or ""),
                authorization=_command_authorizer(
                    request,
                    capability="shop.retry_failed_marketing",
                ),
            )
        except (MarketingAuthorizationRequired, MarketingAuthorizationError) as exc:
            return _authorization_error_response(exc, request)
        except (
            MarketingCommandConflict,
            MarketingCommandRejected,
            MarketingContractError,
        ) as exc:
            return _command_error_response(exc)
        return Response(_command_response(result))


class AnnouncementReconcileDeliveriesView(_CampaignBase):
    """Create lookup-only work for unknown outcomes; this endpoint never sends."""

    permission_map = {"POST": "shop.reconcile_unknown_marketing"}
    throttle_classes = list(_DANGEROUS_THROTTLES)

    def post(self, request, pk: int):
        payload = request.data if isinstance(request.data, dict) else {}
        unexpected = sorted(set(payload) - ({"base_version", "platforms"} | _AUTHORIZATION_FIELDS))
        if unexpected:
            return _unknown_command_fields(unexpected)
        base_version, error = _command_version(payload)
        if error:
            return error
        try:
            from shopman.shop.services.marketing_delivery_recovery import (
                request_reconciliation_command,
            )

            result = request_reconciliation_command(
                pk,
                actor=request.user,
                idempotency_key=str(request.headers.get("Idempotency-Key") or ""),
                base_version=base_version,
                platforms=payload.get("platforms", ()),
                request_id=str(request.headers.get("X-Request-ID") or ""),
                authorization=_command_authorizer(
                    request,
                    capability="shop.reconcile_unknown_marketing",
                ),
            )
        except (MarketingAuthorizationRequired, MarketingAuthorizationError) as exc:
            return _authorization_error_response(exc, request)
        except (
            MarketingCommandConflict,
            MarketingCommandRejected,
            MarketingContractError,
        ) as exc:
            return _command_error_response(exc)
        return Response(_command_response(result))


# ── Regras ───────────────────────────────────────────────────────────


class CampaignListView(_CampaignBase):
    permission_map = {
        "GET": "shop.view_marketing",
        "POST": "shop.edit_marketing_campaigns",
    }

    def get(self, request):
        rules = marketing_projection.build_rules()
        contexts = tuple(
            CampaignActionContext(
                ref=f"campaign:{rule.pk}",
                version=rule.version,
                active=rule.is_active,
            )
            for rule in rules
        )
        actions = tuple(
            action
            for resource_actions in resolve_actions_for(
                contexts,
                actor=request.user,
            )
            for action in resource_actions
        )
        return Response(
            {
                "rules": projection_data(rules),
                "actions": projection_data(actions),
            }
        )

    def post(self, request):
        fields, error = _rule_fields(request.data, partial=False)
        if error:
            return Response(error, status=400)
        rule = Campaign(**fields)
        error = _pairing_error(rule)
        if error:
            return Response(error, status=400)
        rule.save()
        return Response(
            {"ok": True, "rule": projection_data(marketing_projection.build_rule(rule))},
            status=201,
        )


class PreviewView(_CampaignBase):
    """POST campaign/preview/ → como a mensagem vai ficar, antes de existir cliente.

    Variável com nome errado devolve erro no campo antes de aprovar. A tela mostra os valores
    usados sem exigir conferência em aparelho externo.

    Resolve pelo MESMO caminho do envio (`campaign.preview` → `resolve_variables`). Prévia com
    montagem própria concordaria hoje e divergiria no primeiro ajuste, e prévia que mente é
    pior que nenhuma, porque é acreditada.
    """

    permission_map = {"POST": "shop.preview_marketing_audience"}
    throttle_classes = [MarketingAudienceUserThrottle, MarketingAudienceShopThrottle]

    def post(self, request):
        payload = request.data if isinstance(request.data, dict) else {}
        try:
            common = {
                "sku": str(payload.get("sku") or ""),
                "promotion_ref": str(payload.get("promotion_ref") or ""),
                "use_ai": bool(payload.get("use_ai")),
                "platform_content": payload.get("platform_content"),
                "content_version": payload.get("content_version", 1),
            }
            if "platforms" in payload:
                platforms, error = _platforms(payload.get("platforms"))
                if error:
                    raise MarketingContractError(
                        code="invalid_preview_platforms",
                        detail=error["detail"],
                        field_errors={"platforms": (error["detail"],)},
                    )
                preview = campaign_service.preview_platforms(
                    str(payload.get("body") or ""),
                    platforms=platforms,
                    **common,
                )
            else:
                preview = campaign_service.preview(
                    str(payload.get("body") or ""),
                    platform=str(payload.get("platform") or "instagram"),
                    **common,
                )
        except MarketingContractError as exc:
            return _command_error_response(exc)
        return Response(preview)


class AudienceCountView(_CampaignBase):
    """POST marketing/audience/count/ → quantas pessoas este público alcança.

    ⚠️ A tela deixava escolher público às cegas: o tamanho só aparecia depois do envio,
    quando já não tem desfazer. E sem esta contagem a diferença entre somar e cruzar as
    regras era invisível — "leais + atacado" alargava para 5 quando o gestor queria os 2
    que são as duas coisas, e nada na tela contava isso.

    Só números, nunca destinatário: a mesma lei do `Announcement.audience`. E resolve pelo
    caminho do envio, então o que a tela promete é o que sai.
    """

    permission_map = {"POST": "shop.preview_marketing_audience"}
    throttle_classes = [MarketingAudienceUserThrottle, MarketingAudienceShopThrottle]

    def post(self, request):
        payload = request.data if isinstance(request.data, dict) else {}
        rules = payload.get("audience_rules")
        if not isinstance(rules, dict):
            rules = {}
        return Response(
            projection_data(
                marketing_projection.build_audience_count(
                    rules,
                    sku=str(payload.get("sku") or ""),
                )
            )
        )


class PlatformsView(_CampaignBase):
    """GET campaign/platforms/ → por onde a padaria consegue falar, e o que falta.

    A tela que faltava, e cuja ausência explicava os remendos: o estado das plataformas
    vazava para o painel de revisão, primeiro como ação dentro de um alerta, depois como
    botão no cabeçalho. Ver `docs/plans/MARKETING-UX-PLAN.md`.

    Devolve TODA plataforma, pronta ou não — esconder as saudáveis obrigaria o gestor a
    deduzir ausência de aviso como boa notícia.
    """

    def get(self, request):
        platforms = marketing_projection.build_platforms()
        contexts = tuple(
            PlatformActionContext(
                platform_ref=platform.platform,
                version=platform.version,
                state=platform.state,
                in_use=platform.in_use,
            )
            for platform in platforms
        )
        actions = tuple(
            action
            for resource_actions in resolve_actions_for(
                contexts,
                actor=request.user,
            )
            for action in resource_actions
        )
        return Response(
            {
                "platforms": projection_data(platforms),
                "actions": projection_data(actions),
            }
        )


class WhatsAppTemplateView(_CampaignBase):
    """Escolher o template aprovado do WhatsApp, aqui — onde o anúncio é operado.

    O dono corrigiu um erro meu de leitura: "Admin = só config" existe para **limitar o
    Admin**, não para exilar configuração dos apps de operador. Escolher o template com
    que o anúncio sai é inseparável de operar o anúncio — quem decide publicar é quem
    precisa saber e mudar isso, sem trocar de aplicativo.

    O Admin continua podendo (é CRUD legítimo do `NotificationTemplate`); a diferença é
    que agora não é o ÚNICO lugar.

        GET  → templates disponíveis na plataforma + o escolhido agora
        POST → escolher (ou limpar, com string vazia)
    """

    EVENT = "announcement_published"
    permission_map = {
        "GET": "shop.view_marketing",
        "POST": "shop.configure_marketing_platforms",
    }
    throttle_classes = list(_DANGEROUS_THROTTLES)

    def get(self, request):
        from shopman.shop.models import NotificationTemplate
        from shopman.shop.services import delivery_readiness, manychat_flows

        template = NotificationTemplate.objects.filter(event=self.EVENT).first()
        current = (template.whatsapp_flow_ns or "") if template else ""
        catalog = manychat_flows.flow_catalog(force=request.query_params.get("refresh") == "1")
        readiness = delivery_readiness.readiness_for(("whatsapp",))[0]
        can_send_test = request.user.has_perm("shop.send_marketing_test")

        return Response(
            {
                "current": current,
                "current_name": next(
                    (name for ns, name in catalog.flows if ns == current),
                    "",
                ),
                "current_active": bool(template and template.is_active),
                "version": template.version if template else 1,
                "available": [{"ns": ns, "name": name} for ns, name in catalog.flows],
                # Successful empty is known and distinct from outage/no credential.
                "can_list": catalog.state == "fresh",
                "configured": bool(current),
                "command_available": catalog.mutation_safe,
                "command_disabled_reason": ("" if catalog.mutation_safe else "platform_catalog_unavailable"),
                "catalog_state": catalog.state,
                "catalog_checked_at": catalog.checked_at,
                "catalog_as_of": catalog.facts_as_of,
                "catalog_fresh_until": catalog.fresh_until,
                "catalog_hash": catalog.catalog_hash,
                "readiness_state": readiness.state,
                "readiness_reason_code": readiness.reason_code,
                "can_send_test": can_send_test,
                "test_targets": (campaign_service.marketing_test_target_options() if can_send_test else []),
            }
        )

    def post(self, request):
        from shopman.shop.services.marketing_platform_configuration import (
            MarketingPlatformUnavailable,
            configure_whatsapp_flow,
        )

        payload = request.data if isinstance(request.data, dict) else {}
        unexpected = sorted(set(payload) - ({"flow_ns", "base_version"} | _AUTHORIZATION_FIELDS))
        if unexpected:
            return _unknown_command_fields(unexpected)
        base_version, error = _command_version(payload)
        if error:
            return error
        try:
            result = configure_whatsapp_flow(
                actor=request.user,
                flow_ns=str(payload.get("flow_ns") or ""),
                base_version=base_version,
                idempotency_key=str(request.headers.get("Idempotency-Key") or ""),
                request_id=str(request.headers.get("X-Request-ID") or ""),
                authorize=_command_authorizer(
                    request,
                    capability="shop.configure_marketing_platforms",
                ),
            )
        except (MarketingAuthorizationRequired, MarketingAuthorizationError) as exc:
            return _authorization_error_response(exc, request)
        except MarketingPlatformUnavailable as exc:
            response = Response(exc.as_payload(), status=exc.status_code)
            response["Retry-After"] = str(exc.retry_after)
            return response
        except (
            MarketingCommandConflict,
            MarketingCommandRejected,
            MarketingContractError,
        ) as exc:
            return _command_error_response(exc)
        receipt = result.receipt
        return Response(
            {
                "ok": True,
                "replayed": result.replayed,
                "receipt": {
                    "ref": str(receipt.ref),
                    "kind": receipt.kind,
                    "state": receipt.state,
                    "base_version": receipt.base_version,
                    "resulting_version": receipt.resulting_version,
                    "resource_ref": receipt.resource_ref,
                    "outcome": receipt.outcome,
                    "created_at": receipt.created_at.isoformat(),
                    "completed_at": (receipt.completed_at.isoformat() if receipt.completed_at else ""),
                },
            }
        )


class CampaignFireView(_CampaignBase):
    """Criar agora uma ocasião de campanha, sempre pendente de revisão.

    O cliente pode escolher apenas o recorte público canônico. Texto livre é
    deliberadamente desconhecido neste contrato: disparar nunca é um atalho para
    publicar sem o segundo gate de revisão. Versão, idempotência, confirmação,
    snapshot, receipt e audit são fechados na mesma transação.
    """

    permission_map = {"POST": "shop.fire_marketing_campaigns"}
    throttle_classes = [
        *_DANGEROUS_THROTTLES,
        MarketingFireUserThrottle,
        MarketingFireShopThrottle,
    ]

    def post(self, request, pk: int):
        from shopman.shop.services.audience import PUBLIC_RULE_KEYS
        from shopman.shop.services.marketing_fire import fire_campaign_command

        payload = request.data if isinstance(request.data, dict) else {}
        allowed = {"base_version", "audience_rules"} | _AUTHORIZATION_FIELDS
        unexpected = sorted(set(payload) - allowed)
        if unexpected:
            return _unknown_command_fields(unexpected)
        base_version, error = _command_version(payload)
        if error:
            return error

        raw_rules = payload.get("audience_rules")
        if raw_rules is not None and not isinstance(raw_rules, dict):
            return Response(
                {
                    "code": "invalid_audience_rules",
                    "detail": "A configuração do público deve ser um objeto.",
                    "field_errors": {"audience_rules": ["Use filtros válidos do público."]},
                },
                status=422,
            )
        audience_rules = dict(raw_rules or {})
        unknown_rules = sorted(set(audience_rules) - PUBLIC_RULE_KEYS)
        if unknown_rules:
            return Response(
                {
                    "code": "invalid_audience_rules",
                    "detail": "O público contém filtros desconhecidos ou privados.",
                    "field_errors": {"audience_rules": unknown_rules},
                },
                status=422,
            )

        try:
            result = fire_campaign_command(
                pk,
                actor=request.user,
                idempotency_key=str(request.headers.get("Idempotency-Key") or ""),
                base_version=base_version,
                audience_rules=audience_rules or None,
                request_id=str(request.headers.get("X-Request-ID") or ""),
                authorize=_command_authorizer(
                    request,
                    capability="shop.fire_marketing_campaigns",
                ),
            )
        except (MarketingAuthorizationRequired, MarketingAuthorizationError) as exc:
            return _authorization_error_response(exc, request)
        except (
            MarketingCommandConflict,
            MarketingCommandRejected,
            MarketingContractError,
        ) as exc:
            return _command_error_response(exc)

        logger.info(
            "campaign.fire_command actor=%s campaign=%s announcement=%s receipt=%s replayed=%s",
            request.user.pk,
            pk,
            result.announcement.pk,
            result.receipt.ref,
            result.replayed,
        )
        return Response(_command_response(result))


class CampaignDetailView(_CampaignBase):
    permission_map = {
        "GET": "shop.view_marketing",
        "PATCH": "shop.edit_marketing_campaigns",
        "DELETE": "shop.edit_marketing_campaigns",
    }

    def get(self, request, pk: int):
        rule = _rule_or_none(pk)
        if rule is None:
            return Response({"detail": "Regra não encontrada."}, status=404)
        actions = resolve_actions(rule, actor=request.user)
        return Response(
            {
                "rule": projection_data(marketing_projection.build_rule(rule)),
                "actions": projection_data(actions),
            }
        )

    def patch(self, request, pk: int):
        with transaction.atomic():
            rule = Campaign.objects.select_for_update().select_related("template").filter(pk=pk).first()
            if rule is None:
                return Response({"detail": "Regra não encontrada."}, status=404)
            guarded = _updated_at_guard(request.data, rule.updated_at)
            if guarded:
                payload, status_code = guarded
                payload["current"] = projection_data(marketing_projection.build_rule(rule))
                return Response(payload, status=status_code)

            fields, error = _rule_fields(request.data, partial=True)
            if error:
                return Response(error, status=400)
            if "audience_rules" in fields:
                fields["audience_rules"] = _merge_public_audience_rules(
                    rule.audience_rules,
                    fields["audience_rules"],
                )
            for name, value in fields.items():
                setattr(rule, name, value)
            error = _pairing_error(rule)
            if error:
                return Response(error, status=400)
            rule.version += 1
            rule.save()
        return Response({"ok": True, "rule": projection_data(marketing_projection.build_rule(rule))})

    def delete(self, request, pk: int):
        rule = _rule_or_none(pk)
        if rule is None:
            return Response({"detail": "Regra não encontrada."}, status=404)
        rule.delete()
        return Response({"ok": True, "pk": pk})


# ── Modelos de announcement ──────────────────────────────────────────────────


class AnnouncementTemplateListView(_CampaignBase):
    permission_map = {
        "GET": "shop.view_marketing",
        "POST": "shop.edit_marketing_templates",
    }

    def get(self, request):
        return Response({"templates": projection_data(marketing_projection.build_templates())})

    def post(self, request):
        fields, error = _template_fields(request.data, partial=False)
        if error:
            return Response(error, status=400)
        template = AnnouncementTemplate.objects.create(**fields)
        return Response(
            {"ok": True, "template": projection_data(marketing_projection.build_template(template))},
            status=201,
        )


class AnnouncementTemplateDetailView(_CampaignBase):
    permission_map = {
        "GET": "shop.view_marketing",
        "PATCH": "shop.edit_marketing_templates",
        "DELETE": "shop.edit_marketing_templates",
    }

    def get(self, request, pk: int):
        template = AnnouncementTemplate.objects.filter(pk=pk).first()
        if template is None:
            return Response({"detail": "Modelo não encontrado."}, status=404)
        return Response({"template": projection_data(marketing_projection.build_template(template))})

    def patch(self, request, pk: int):
        with transaction.atomic():
            template = AnnouncementTemplate.objects.select_for_update().filter(pk=pk).first()
            if template is None:
                return Response({"detail": "Modelo não encontrado."}, status=404)
            guarded = _updated_at_guard(request.data, template.updated_at)
            if guarded:
                payload, status_code = guarded
                payload["current"] = projection_data(marketing_projection.build_template(template))
                return Response(payload, status=status_code)

            fields, error = _template_fields(request.data, partial=True)
            if error:
                return Response(error, status=400)
            for name, value in fields.items():
                setattr(template, name, value)
            template.save()
        return Response({"ok": True, "template": projection_data(marketing_projection.build_template(template))})

    def delete(self, request, pk: int):
        template = AnnouncementTemplate.objects.filter(pk=pk).first()
        if template is None:
            return Response({"detail": "Modelo não encontrado."}, status=404)
        try:
            template.delete()
        except ProtectedError:
            # ``Campaign.template`` é PROTECT: apagar o modelo deixaria
            # regras órfãs disparando no vazio.
            return Response(
                {"detail": "Há regras usando este modelo. Desative ou troque o modelo delas."},
                status=400,
            )
        return Response({"ok": True, "pk": pk})


# ── Validação e leitura de payload ───────────────────────────────────


def _offer_exists(ref: str) -> bool:
    """A oferta existe e ainda vale? Perguntado na hora de SALVAR a campanha.

    Salvar uma campanha apontando para oferta morta produziria anúncio com link que
    responde 404 — e o gestor só descobriria pelo cliente reclamando.
    """
    from shopman.shop.services import offers as offer_service

    try:
        offer_service.get_offer(ref, channel_ref="")
    except offer_service.OfferUnavailable:
        return False
    return True


def _pairing_error(rule: Campaign) -> dict | None:
    """A validação de gatilho×agendamento do model, no dialeto de erro da API.

    O `clean()` do model é o dono da regra, mas Django só o chama em formulário — o
    Admin chamava, esta API não. Sem esta ponte, o app do gestor salvaria a campanha
    agendada que nunca dispara, e a mesma pergunta teria duas respostas.
    """
    try:
        rule.clean()
    except DjangoValidationError as exc:
        errors = exc.message_dict
        field = next(iter(errors), "schedule")
        return {"detail": errors[field][0], "field": field}
    return None


def _rule_fields(data, *, partial: bool) -> tuple[dict, dict | None]:
    """Campos válidos de uma regra, ou o erro no dialeto canônico."""
    fields: dict = {}

    if not isinstance(data, dict):
        return {}, {"detail": "Payload da regra inválido.", "field": "payload"}
    allowed = {
        "audience_rules",
        "expires_after_minutes",
        "is_active",
        "name",
        "notify_users",
        "platforms",
        "promotion_ref",
        "requires_approval",
        "schedule",
        "template_id",
        "trigger",
        "trigger_filter",
    }
    if partial:
        allowed.add("base_updated_at")
    unexpected = sorted(set(data) - allowed)
    if unexpected:
        return {}, {
            "detail": "A regra contém campos desconhecidos.",
            "field": "payload",
            "fields": unexpected,
        }

    if not partial or "name" in data:
        name = str(data.get("name") or "").strip()
        if not name:
            return {}, {"detail": "A regra precisa de um nome.", "field": "name"}
        fields["name"] = name

    if not partial or "trigger" in data:
        trigger = str(data.get("trigger") or "").strip()
        if trigger not in Trigger.values:
            return {}, {"detail": "Gatilho desconhecido.", "field": "trigger"}
        fields["trigger"] = trigger

    if not partial or "template_id" in data:
        template = AnnouncementTemplate.objects.filter(pk=_as_int(data.get("template_id"))).first()
        if template is None:
            return {}, {"detail": "Modelo de anúncio não encontrado.", "field": "template_id"}
        fields["template"] = template

    if not partial or "platforms" in data:
        platforms, error = _platforms(data.get("platforms"))
        if error:
            return {}, error
        if not platforms:
            return {}, {
                "detail": "Escolha ao menos uma plataforma.",
                "field": "platforms",
            }
        fields["platforms"] = platforms

    for name in ("trigger_filter", "audience_rules", "schedule"):
        if name in data:
            value = data.get(name)
            if not isinstance(value, dict):
                return {}, {"detail": "Configuração inválida.", "field": name}
            if name == "audience_rules":
                from shopman.shop.services.audience import PUBLIC_RULE_KEYS

                unknown = sorted(set(value) - PUBLIC_RULE_KEYS)
                if unknown:
                    return {}, {
                        "detail": "A audiência contém campos desconhecidos ou privados.",
                        "field": "audience_rules",
                        "fields": unknown,
                    }
            fields[name] = value

    if not partial or "promotion_ref" in data:
        offer_ref = str(data.get("promotion_ref") or "").strip()
        if offer_ref and not _offer_exists(offer_ref):
            return {}, {
                "detail": "Esta oferta não existe ou não vale mais.",
                "field": "promotion_ref",
            }
        fields["promotion_ref"] = offer_ref

    if "notify_users" in data:
        fields["notify_users"] = [int(uid) for uid in (data.get("notify_users") or []) if str(uid).isdigit()]

    if "requires_approval" in data:
        fields["requires_approval"] = bool(data.get("requires_approval"))
    if "is_active" in data:
        fields["is_active"] = bool(data.get("is_active"))
    if "expires_after_minutes" in data:
        minutes = _as_int(data.get("expires_after_minutes"))
        if minutes is None or minutes < 0:
            return {}, {
                "detail": "O prazo precisa ser um número de minutos (0 = não expira).",
                "field": "expires_after_minutes",
            }
        fields["expires_after_minutes"] = minutes

    return fields, None


def _merge_public_audience_rules(current, incoming: dict) -> dict:
    """Replace the public schema while preserving private/legacy server state."""

    from shopman.shop.services.audience import PUBLIC_RULE_KEYS

    existing = current if isinstance(current, dict) else {}
    private_or_legacy = {key: value for key, value in existing.items() if key not in PUBLIC_RULE_KEYS}
    return {**private_or_legacy, **incoming}


def _template_fields(data, *, partial: bool) -> tuple[dict, dict | None]:
    fields: dict = {}

    if not isinstance(data, dict):
        return {}, {"detail": "Payload do modelo inválido.", "field": "payload"}
    allowed = {
        "ai_prompt",
        "body",
        "image_source",
        "is_active",
        "name",
        "platform_variants",
        "use_ai_generation",
        "variables",
    }
    if partial:
        allowed.add("base_updated_at")
    unexpected = sorted(set(data) - allowed)
    if unexpected:
        return {}, {
            "detail": "O modelo contém campos desconhecidos.",
            "field": "payload",
            "fields": unexpected,
        }

    if not partial or "name" in data:
        name = str(data.get("name") or "").strip()
        if not name:
            return {}, {"detail": "O modelo precisa de um nome.", "field": "name"}
        fields["name"] = name

    if not partial or "body" in data:
        body = str(data.get("body") or "").strip()
        if not body:
            return {}, {"detail": "O modelo precisa de um texto.", "field": "body"}
        fields["body"] = body

    if "image_source" in data:
        source = str(data.get("image_source") or "").strip()
        if source not in AnnouncementTemplate.ImageSource.values:
            return {}, {"detail": "Origem de imagem desconhecida.", "field": "image_source"}
        fields["image_source"] = source

    if "platform_variants" in data:
        variants = data.get("platform_variants")
        if not isinstance(variants, dict):
            return {}, {"detail": "Variações inválidas.", "field": "platform_variants"}
        fields["platform_variants"] = variants

    if "variables" in data:
        fields["variables"] = _string_list(data.get("variables"))
    if "ai_prompt" in data:
        from shopman.shop.services.marketing_ai import (
            MarketingAIError,
            validate_instruction,
        )

        try:
            fields["ai_prompt"] = validate_instruction(data.get("ai_prompt") or "")
        except MarketingAIError as exc:
            return {}, {"detail": exc.detail, "field": "ai_prompt", "code": exc.code}
    if "use_ai_generation" in data:
        fields["use_ai_generation"] = bool(data.get("use_ai_generation"))
    if "is_active" in data:
        fields["is_active"] = bool(data.get("is_active"))

    return fields, None


def _updated_at_guard(data, current) -> tuple[dict, int] | None:
    """Optimistic lock for CRUD resources that already own an ``updated_at`` clock."""

    if not isinstance(data, dict) or "base_updated_at" not in data:
        return None
    from django.utils.dateparse import parse_datetime

    raw = data.get("base_updated_at")
    parsed = parse_datetime(str(raw)) if raw else None
    if parsed is None:
        return (
            {
                "code": "invalid_base_version",
                "detail": "A versão de leitura é inválida.",
                "field_errors": {"base_updated_at": ["Recarregue o conteúdo atual."]},
            },
            422,
        )
    if parsed != current:
        return (
            {
                "code": "version_conflict",
                "detail": "O conteúdo mudou enquanto você editava.",
                "current_version": current.isoformat(),
                "field_errors": {"base_updated_at": ["Compare com a versão atual."]},
            },
            409,
        )
    return None


def _announcement_edits(data) -> tuple[dict, dict | None]:
    """Edições do card. Chave ausente ≠ campo apagado — só muda o que veio."""
    edits: dict = {}

    if "body" in data:
        body = str(data.get("body") or "").strip()
        if not body:
            return {}, {"detail": "O texto do anúncio não pode ficar vazio.", "field": "body"}
        edits["body"] = body
    if "hashtags" in data:
        edits["hashtags"] = _string_list(data.get("hashtags"))
    if "image_url" in data:
        edits["image_url"] = str(data.get("image_url") or "").strip()
    if "platforms" in data:
        platforms, error = _platforms(data.get("platforms"))
        if error:
            return {}, error
        if not platforms:
            return {}, {"detail": "Escolha ao menos uma plataforma.", "field": "platforms"}
        edits["platforms"] = platforms

    return edits, None


def _is_approval_command(request) -> bool:
    """A v2-shaped attempt must never downgrade to the legacy approval path."""

    data = request.data if isinstance(request.data, dict) else {}
    return bool(request.headers.get("Idempotency-Key") or "base_version" in data or "publish_mode" in data)


def _command_version(payload) -> tuple[int, Response | None]:
    raw = payload.get("base_version")
    version = None if isinstance(raw, bool) else _as_int(raw)
    if version is None or version <= 0:
        return 0, Response(
            {
                "code": "invalid_base_version",
                "detail": "Informe a versão exibida na revisão.",
                "field_errors": {"base_version": ["Use um inteiro positivo."]},
            },
            status=422,
        )
    return version, None


def _unknown_command_fields(fields: list[str]) -> Response:
    return Response(
        {
            "code": "unknown_command_fields",
            "detail": "O comando contém campos desconhecidos.",
            "field_errors": {"payload": fields},
        },
        status=422,
    )


def _command_protocol_required() -> Response:
    return Response(
        {
            "code": "command_protocol_required",
            "detail": (
                "Atualize esta ação: versão, Idempotency-Key e confirmação são obrigatórias antes de qualquer efeito."
            ),
        },
        status=409,
    )


def _command_authorizer(
    request,
    *,
    capability: str,
    additional_capabilities: tuple[str, ...] = (),
):
    from shopman.shop.services.marketing_security import (
        authorize_command,
        step_up_evidence_from_session,
    )

    payload = request.data if isinstance(request.data, dict) else {}
    token = str(payload.get("confirmation_token") or "")
    typed = str(payload.get("typed_confirmation") or "")
    evidence = step_up_evidence_from_session(request)

    def authorize(context, receipt):
        authorize_command(
            actor=request.user,
            capability=capability,
            additional_capabilities=additional_capabilities,
            context=context,
            token=token,
            typed_confirmation=typed,
            step_up=evidence,
            command=receipt,
        )

    return authorize


def _authorization_error_response(
    exc: MarketingAuthorizationRequired | MarketingAuthorizationError,
    request,
) -> Response:
    from shopman.shop.services.marketing_security import (
        issue_confirmation,
        record_security_denial,
    )

    if isinstance(exc, MarketingAuthorizationRequired):
        try:
            payload = issue_confirmation(exc, actor=request.user)
        except MarketingAuthorizationError as issue_error:
            return _authorization_error_response(issue_error, request)
        return Response(payload, status=428)
    record_security_denial(
        actor=request.user,
        reason_code=exc.code,
        action="command_denied",
    )
    response = Response(exc.as_payload(), status=exc.status_code)
    if exc.retry_after is not None:
        response["Retry-After"] = str(exc.retry_after)
    return response


def _safety_payload(state) -> dict:
    return {
        "frozen": state.frozen,
        "version": state.version,
        "generation": state.generation,
        "reason": state.reason if state.frozen else "",
        "frozen_at": state.frozen_at.isoformat() if state.frozen_at else "",
    }


def _command_error_response(
    exc: MarketingCommandConflict | MarketingCommandRejected | MarketingContractError,
) -> Response:
    if isinstance(exc, MarketingCommandConflict):
        return Response(exc.as_payload(), status=409)
    if isinstance(exc, MarketingCommandRejected):
        status_code = 404 if exc.code in {"announcement_not_found", "campaign_not_found"} else 422
        return Response(exc.as_payload(), status=status_code)
    status_code = int(getattr(exc, "status_code", 422))
    response = Response(exc.as_payload(), status=status_code)
    retry_after = getattr(exc, "retry_after", None)
    if retry_after is not None:
        response["Retry-After"] = str(retry_after)
    return response


def _command_response(result) -> dict:
    receipt = result.receipt
    return {
        "ok": True,
        "replayed": result.replayed,
        "receipt": {
            "ref": str(receipt.ref),
            "kind": receipt.kind,
            "state": receipt.state,
            "base_version": receipt.base_version,
            "resulting_version": receipt.resulting_version,
            "resource_ref": receipt.resource_ref,
            "outcome": receipt.outcome,
            "created_at": receipt.created_at.isoformat(),
            "completed_at": (receipt.completed_at.isoformat() if receipt.completed_at else ""),
        },
        "announcement": projection_data(marketing_projection.build_announcement(result.announcement)),
    }


def _publish_at(raw, *, timezone_name: str = "") -> tuple[object | None, dict | None]:
    """ISO 8601 + named zone → one verified instant. Empty means publish now."""
    if timezone_name:
        from shopman.shop.services import marketing_time

        try:
            marketing_time.require_configured_timezone(timezone_name)
        except ValueError as exc:
            code = str(exc)
            return None, {
                "code": code,
                "detail": (
                    "O timezone não corresponde ao configurado para a loja."
                    if code == "timezone_mismatch"
                    else "O timezone informado não existe."
                ),
                "field": "publish_timezone",
            }
    if raw in (None, ""):
        return None, None

    from django.utils import timezone
    from django.utils.dateparse import parse_datetime

    parsed = parse_datetime(str(raw))
    if parsed is None:
        return None, {
            "detail": "Data inválida. Use o formato ISO (2026-07-18T07:00).",
            "field": "publish_at",
        }
    if timezone_name and timezone.is_naive(parsed):
        return None, {
            "code": "scheduled_publish_at_naive",
            "detail": "A data agendada precisa incluir o offset do horário.",
            "field": "publish_at",
        }
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
    if timezone_name:
        from shopman.shop.services import marketing_time

        try:
            parsed = marketing_time.validate_named_instant(
                parsed,
                timezone_name=timezone_name,
            )
        except ValueError:
            return None, {
                "code": "timezone_offset_mismatch",
                "detail": "O offset não corresponde à data nesse timezone.",
                "field": "publish_at",
            }
    return parsed, None


def _platforms(raw) -> tuple[list[str], dict | None]:
    if not isinstance(raw, list | tuple):
        return [], {"detail": "Plataformas inválidas.", "field": "platforms"}
    platforms = [str(item).strip() for item in raw if str(item).strip()]
    unknown = [item for item in platforms if item not in _VALID_PLATFORMS]
    if unknown:
        return [], {
            "detail": f"Plataforma desconhecida: {', '.join(unknown)}.",
            "field": "platforms",
        }
    return platforms, None


def _string_list(raw) -> list[str]:
    if isinstance(raw, str):
        raw = raw.split(",")
    if not isinstance(raw, list | tuple):
        return []
    return [str(item).strip().lstrip("#") for item in raw if str(item).strip()]


def _announcement_or_none(pk: int) -> Announcement | None:
    return Announcement.objects.select_related("rule", "template", "approved_by").filter(pk=pk).first()


def _rule_or_none(pk: int) -> Campaign | None:
    return Campaign.objects.select_related("template").filter(pk=pk).first()


def _as_bool(value) -> bool:
    """JSON manda ``true``; form-data manda ``"true"``. Os dois valem."""
    if isinstance(value, str):
        return value.strip().lower() in ("true", "1", "yes", "on")
    return bool(value)


def _as_int(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _limit(request) -> int:
    raw = request.query_params.get("limit")
    try:
        return max(1, min(int(raw), _HISTORY_MAX_LIMIT)) if raw else _HISTORY_DEFAULT_LIMIT
    except (TypeError, ValueError):
        return _HISTORY_DEFAULT_LIMIT


def _history_v2_limit(request) -> int:
    raw = str(request.query_params.get("limit") or "").strip()
    if not raw:
        return _HISTORY_V2_DEFAULT_LIMIT
    try:
        value = int(raw)
    except ValueError as exc:
        raise MarketingV2Problem(
            status_code=422,
            code="invalid_limit",
            detail="presentation.invalid_limit",
            field_errors={"limit": ("presentation.invalid_limit",)},
        ) from exc
    if value < 1 or value > _HISTORY_V2_MAX_LIMIT:
        raise MarketingV2Problem(
            status_code=422,
            code="invalid_limit",
            detail="presentation.invalid_limit",
            field_errors={"limit": ("presentation.limit_out_of_range",)},
        )
    return value
