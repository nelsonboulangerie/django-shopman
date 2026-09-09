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
from django.db.models import ProtectedError
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema, extend_schema_view
from rest_framework.response import Response
from rest_framework.views import APIView

from shopman.backstage.api.permissions import HasMarketingCapability
from shopman.backstage.api.projections import projection_data
from shopman.backstage.projections import marketing as marketing_projection
from shopman.shop.models import Announcement, AnnouncementStatus, AnnouncementTemplate, Campaign, Trigger
from shopman.shop.services import campaign as campaign_service

logger = logging.getLogger(__name__)

_HISTORY_DEFAULT_LIMIT = 100
_HISTORY_MAX_LIMIT = 300

#: Plataformas aceitas numa regra — mesma lista que a tela oferece.
_VALID_PLATFORMS = {ref for ref, _ in marketing_projection.PLATFORM_CHOICES}


class _CampaignBase(APIView):
    permission_classes = [HasMarketingCapability]
    permission_map = {"GET": "shop.view_marketing"}

    def get_required_permissions(self, request):
        return self.permission_map.get(request.method, ())


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
        return Response({"announcement": projection_data(marketing_projection.build_announcement(announcement))})

    def patch(self, request, pk: int):
        announcement = _announcement_or_none(pk)
        if announcement is None:
            return Response({"detail": "Anúncio não encontrado."}, status=404)
        if announcement.status not in (AnnouncementStatus.DRAFT, AnnouncementStatus.PENDING_REVIEW):
            return Response(
                {"detail": "Este announcement já saiu. Não dá para reescrever o que já foi lido."},
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

        # Pelo serviço, não direto no model: ele reprojeta ``platform_content``
        # a partir do corpo editado. Salvar só ``content`` deixaria a variação
        # por plataforma com o texto velho — o gestor editaria no vazio.
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
        except campaign_service.CampaignError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response({"ok": True, "announcement": projection_data(marketing_projection.build_announcement(announcement))})


class AnnouncementApproveView(_CampaignBase):
    """Publicar — agora ou na hora marcada.

    O serviço cria uma Directive por plataforma (retry de graça). As edições do
    card vão no MESMO request: salvar e aprovar em duas chamadas abriria a
    janela para publicar a versão anterior.
    """

    permission_map = {
        "POST": (
            "shop.approve_marketing_announcements",
            "shop.publish_marketing_announcements",
        ),
    }

    def post(self, request, pk: int):
        # Additive v2 migration: a caller that declares version/publish_mode is a
        # command caller and can never fall through to the non-idempotent legacy
        # path. Old clients remain readable until the cutover task removes it.
        if _is_approval_command(request):
            return self._post_command(request, pk)

        publish_at, error = _publish_at(request.data.get("publish_at"))
        if error:
            return Response(error, status=400)

        edits, error = _announcement_edits(request.data)
        if error:
            return Response(error, status=400)

        try:
            if edits:
                campaign_service.update_content(pk, **edits)
            announcement = campaign_service.approve(
                pk, request.user,
                publish_at=publish_at,
                # "Publicar agora" vence a janela preferida da regra; sem ele,
                # aprovar fora do horário aceita a hora que a regra sugeriu.
                respect_schedule=not _as_bool(request.data.get("publish_now")),
            )
        except campaign_service.CampaignError as exc:
            return Response({"detail": str(exc)}, status=400)

        logger.info(
            "campaign.approved user=%s announcement=%s publish_at=%s",
            request.user.pk, pk, publish_at or "now",
        )
        return Response({
            "ok": True,
            "scheduled": bool(announcement.publish_at),
            "announcement": projection_data(marketing_projection.build_announcement(announcement)),
        })

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
        }
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
        publish_at, error = _publish_at(payload.get("publish_at"))
        if error:
            return Response(
                {
                    "code": "invalid_publish_at",
                    "detail": error["detail"],
                    "field_errors": {"publish_at": [error["detail"]]},
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
                campaign_service._platform_content(announcement.template, content)
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
                content=content,
                platform_content=platform_content,
                platforms=platforms,
                request_id=str(request.headers.get("X-Request-ID") or ""),
                # Fingerprint only the normalized client intention. Server-side
                # enrichment may change after a conflict, but replaying the same
                # HTTP command must still retrieve its original receipt.
                idempotency_payload={
                    "edits": edits,
                    "publish_at": publish_at.isoformat() if publish_at else "",
                    "publish_mode": publish_mode,
                },
            )
        except MarketingCommandConflict as exc:
            return Response(exc.as_payload(), status=409)
        except MarketingCommandRejected as exc:
            status_code = 404 if exc.code == "announcement_not_found" else 422
            return Response(exc.as_payload(), status=status_code)
        except MarketingContractError as exc:
            return Response(exc.as_payload(), status=422)

        receipt = result.receipt
        logger.info(
            "campaign.approval_command actor=%s announcement=%s receipt=%s replayed=%s",
            request.user.pk,
            pk,
            receipt.ref,
            result.replayed,
        )
        return Response({
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
                "completed_at": (
                    receipt.completed_at.isoformat() if receipt.completed_at else ""
                ),
            },
            "announcement": projection_data(
                marketing_projection.build_announcement(result.announcement)
            ),
        })


class WhatsAppTestSendView(_CampaignBase):
    """POST campaign/whatsapp-template/test/ → teste sandbox unitário.

    Fica ao lado da escolha do template porque é a mesma pergunta: "isto renderiza como eu
    escrevi?". Mandar o gestor abrir um terminal para descobrir seria transformar uma
    conferência de dez segundos em tarefa de infraestrutura.

    O operador escolhe uma ref allowlisted; telefone/subscriber não entra no payload,
    resposta ou log. A lane é separada de audiência e deixa receipt idempotente.
    """

    permission_map = {"POST": "shop.send_marketing_test"}

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
            request.user.pk, outcome.receipt_ref, outcome.state, outcome.replayed,
        )
        return Response({
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
        })


class AnnouncementRewriteView(_CampaignBase):
    """POST campaign/announcements/<pk>/rewrite/ → sugestão de corpo pela IA.

    Não grava: devolve a sugestão para o gestor aceitar ou descartar no card, e quem
    persiste é o PATCH. Mesmo desenho do assist do catálogo, por campo e nunca em lote.

    503 quando o ambiente não tem credencial: a tela mostra aviso, não erro. Assist é
    conveniência, não caminho crítico — se ele falhar, o anúncio do template continua lá.
    """

    permission_map = {"POST": "shop.edit_marketing_templates"}

    def post(self, request, pk: int):
        from shopman.shop.services import copy_assist

        payload = request.data if isinstance(request.data, dict) else {}
        try:
            suggestion = campaign_service.rewrite_body(
                pk, current_body=str(payload.get("body") or "")
            )
        except copy_assist.CopyAssistNotConfigured as exc:
            return Response({"detail": str(exc)}, status=503)
        except copy_assist.CopyAssistError as exc:
            return Response({"detail": str(exc)}, status=502)
        except campaign_service.CampaignError as exc:
            return Response({"detail": str(exc)}, status=400)

        return Response({"suggestion": suggestion})


class AnnouncementRejectView(_CampaignBase):
    """Recusar sem publicar: o gestor viu e disse não.

    O motivo vem do corpo e é opcional. Quem recusou fica registrado — recusa anônima
    num balcão com quatro pessoas no turno não é auditável.
    """

    permission_map = {"POST": "shop.approve_marketing_announcements"}

    def post(self, request, pk: int):
        payload = request.data if isinstance(request.data, dict) else {}
        reason = str(payload.get("reason") or "").strip()

        if request.headers.get("Idempotency-Key") or "base_version" in payload:
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
            except Exception as exc:
                response = _command_error_response(exc)
                if response is not None:
                    return response
                raise
            return Response(_command_response(result))

        try:
            announcement = campaign_service.reject(pk, request.user, reason=reason)
        except campaign_service.CampaignError as exc:
            return Response({"detail": str(exc)}, status=400)

        logger.info(
            "campaign.rejected user=%s announcement=%s reason=%r",
            request.user.pk, pk, reason,
        )
        return Response({"ok": True, "announcement": projection_data(marketing_projection.build_announcement(announcement))})


class AnnouncementCancelView(_CampaignBase):
    """Cancel every outbox lane only while none has started."""

    permission_map = {"POST": "shop.publish_marketing_announcements"}

    def post(self, request, pk: int):
        payload = request.data if isinstance(request.data, dict) else {}
        unexpected = sorted(set(payload) - {"base_version"})
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
                request_id=str(request.headers.get("X-Request-ID") or ""),
            )
        except Exception as exc:
            response = _command_error_response(exc)
            if response is not None:
                return response
            raise
        return Response(_command_response(result))


class AnnouncementRescheduleView(_CampaignBase):
    """Move all pending lanes while preserving their relative wave delay."""

    permission_map = {"POST": "shop.publish_marketing_announcements"}

    def post(self, request, pk: int):
        payload = request.data if isinstance(request.data, dict) else {}
        unexpected = sorted(set(payload) - {"base_version", "publish_at"})
        if unexpected:
            return _unknown_command_fields(unexpected)
        base_version, error = _command_version(payload)
        if error:
            return error
        publish_at, parse_error = _publish_at(payload.get("publish_at"))
        if parse_error or publish_at is None:
            detail = (
                parse_error["detail"]
                if parse_error
                else "Escolha a nova data e hora."
            )
            return Response(
                {
                    "code": "invalid_publish_at",
                    "detail": detail,
                    "field_errors": {"publish_at": [detail]},
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
                request_id=str(request.headers.get("X-Request-ID") or ""),
            )
        except Exception as exc:
            response = _command_error_response(exc)
            if response is not None:
                return response
            raise
        return Response(_command_response(result))


# ── Regras ───────────────────────────────────────────────────────────


class CampaignListView(_CampaignBase):
    permission_map = {
        "GET": "shop.view_marketing",
        "POST": "shop.edit_marketing_campaigns",
    }

    def get(self, request):
        return Response({"rules": projection_data(marketing_projection.build_rules())})

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

    Até agora o gestor escrevia `{{product_name}}` e só via o resultado quando a mensagem
    chegava no celular de alguém. Variável com nome errado renderiza vazio em SILÊNCIO — foi
    assim que passaram um `customer_name` que ninguém mandava e uma foto relativa que a Meta
    não carrega.

    Resolve pelo MESMO caminho do envio (`campaign.preview` → `resolve_variables`). Prévia com
    montagem própria concordaria hoje e divergiria no primeiro ajuste, e prévia que mente é
    pior que nenhuma, porque é acreditada.
    """

    permission_map = {"POST": "shop.preview_marketing_audience"}

    def post(self, request):
        payload = request.data if isinstance(request.data, dict) else {}
        return Response(campaign_service.preview(
            str(payload.get("body") or ""),
            sku=str(payload.get("sku") or ""),
            promotion_ref=str(payload.get("promotion_ref") or ""),
            use_ai=bool(payload.get("use_ai")),
        ))


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

    def post(self, request):
        payload = request.data if isinstance(request.data, dict) else {}
        rules = payload.get("audience_rules")
        if not isinstance(rules, dict):
            rules = {}
        return Response(projection_data(marketing_projection.build_audience_count(
            rules, sku=str(payload.get("sku") or ""),
        )))


class PlatformsView(_CampaignBase):
    """GET campaign/platforms/ → por onde a padaria consegue falar, e o que falta.

    A tela que faltava, e cuja ausência explicava os remendos: o estado das plataformas
    vazava para o painel de revisão, primeiro como ação dentro de um alerta, depois como
    botão no cabeçalho. Ver `docs/plans/MARKETING-UX-PLAN.md`.

    Devolve TODA plataforma, pronta ou não — esconder as saudáveis obrigaria o gestor a
    deduzir ausência de aviso como boa notícia.
    """

    def get(self, request):
        return Response({"platforms": projection_data(marketing_projection.build_platforms())})


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

    def get(self, request):
        from shopman.shop.models import NotificationTemplate
        from shopman.shop.services import manychat_flows

        template = NotificationTemplate.objects.filter(event=self.EVENT).first()
        current = (template.whatsapp_flow_ns or "") if template else ""
        flows = manychat_flows.list_flows()
        can_send_test = request.user.has_perm("shop.send_marketing_test")

        return Response({
            "current": current,
            # Lista vazia não é "não existe template": é "não consegui perguntar".
            # A tela precisa distinguir para não afirmar o que não sabe.
            "available": [{"ns": ns, "name": name} for ns, name in flows],
            "can_list": bool(flows),
            "configured": bool(current),
            "can_send_test": can_send_test,
            "test_targets": (
                campaign_service.marketing_test_target_options()
                if can_send_test
                else []
            ),
        })

    def post(self, request):
        from shopman.shop.models import NotificationTemplate
        from shopman.shop.services import manychat_flows

        payload = request.data if isinstance(request.data, dict) else {}
        ns = str(payload.get("flow_ns") or "").strip()

        # Só valida contra a lista quando ela existe: com a API do provedor fora,
        # recusar seria travar o operador por indisponibilidade de terceiro.
        known = {candidate for candidate, _name in manychat_flows.list_flows()}
        if ns and known and ns not in known:
            return Response(
                {"detail": "Este template não existe mais na plataforma.", "field": "flow_ns"},
                status=400,
            )

        template, _created = NotificationTemplate.objects.get_or_create(
            event=self.EVENT,
            defaults={"subject": "Novidade na padaria", "body": "{body}"},
        )
        template.whatsapp_flow_ns = ns
        template.save(update_fields=["whatsapp_flow_ns"])

        return Response({"ok": True, "current": ns, "configured": bool(ns)})


class CampaignFireView(_CampaignBase):
    """Disparar uma campanha AGORA, opcionalmente escolhendo o público.

    A Action que faltava: até aqui um anúncio só nascia de evento operacional, então
    "quero avisar meus clientes hoje" não tinha caminho nenhum. `Trigger.MANUAL` tem
    produtor real, e é este endpoint.

    `body` é o texto escrito na hora. Com ele, o anúncio **publica direto**: não há segundo
    par de olhos quando o autor e o revisor são a mesma pessoa. Sem ele, o texto vem do
    modelo e a revisão segue valendo, porque aí quem escreveu foi o sistema.

    `audience_rules` no corpo vale só PARA ESTE DISPARO — a campanha salva mantém o
    público dela. Assim a mesma campanha serve a públicos diferentes em semanas
    diferentes sem o gestor editar e desfazer a configuração.

    O anúncio nasce pelo mesmo caminho do automático (`_create_announcement`), então
    respeita expiração e janela de agendamento — disparar manual não inventa um segundo
    caminho de criação.
    """

    permission_map = {"POST": "shop.fire_marketing_campaigns"}

    def post(self, request, pk: int):
        from shopman.shop.services import campaign as campaign_service

        payload = request.data if isinstance(request.data, dict) else {}

        audience_rules = payload.get("audience_rules")
        if audience_rules is not None and not isinstance(audience_rules, dict):
            return Response(
                {"detail": "audience_rules deve ser um objeto.", "field": "audience_rules"},
                status=400,
            )

        context = payload.get("context")
        if context is not None and not isinstance(context, dict):
            return Response(
                {"detail": "context deve ser um objeto.", "field": "context"}, status=400
            )

        body = str(payload.get("body") or "").strip()

        try:
            announcement = campaign_service.fire_now(
                pk,
                context=context,
                audience_rules=audience_rules,
                # Texto escrito na hora publica direto, com o nome de quem escreveu.
                body=body,
                author=request.user,
            )
        except campaign_service.CampaignError as exc:
            return Response({"detail": str(exc)}, status=400)

        return Response(
            {
                "ok": True,
                "announcement": projection_data(
                    marketing_projection.build_announcement(announcement)
                ),
            },
            status=201,
        )


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
        return Response({"rule": projection_data(marketing_projection.build_rule(rule))})

    def patch(self, request, pk: int):
        rule = _rule_or_none(pk)
        if rule is None:
            return Response({"detail": "Regra não encontrada."}, status=404)

        fields, error = _rule_fields(request.data, partial=True)
        if error:
            return Response(error, status=400)
        for name, value in fields.items():
            setattr(rule, name, value)
        error = _pairing_error(rule)
        if error:
            return Response(error, status=400)
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
        template = AnnouncementTemplate.objects.filter(pk=pk).first()
        if template is None:
            return Response({"detail": "Modelo não encontrado."}, status=404)

        fields, error = _template_fields(request.data, partial=True)
        if error:
            return Response(error, status=400)
        for name, value in fields.items():
            setattr(template, name, value)
        template.save()
        return Response(
            {"ok": True, "template": projection_data(marketing_projection.build_template(template))}
        )

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
            return {}, {"detail": "Modelo de announcement não encontrado.", "field": "template_id"}
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
        fields["notify_users"] = [
            int(uid) for uid in (data.get("notify_users") or []) if str(uid).isdigit()
        ]

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


def _template_fields(data, *, partial: bool) -> tuple[dict, dict | None]:
    fields: dict = {}

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
        fields["ai_prompt"] = str(data.get("ai_prompt") or "").strip()
    if "use_ai_generation" in data:
        fields["use_ai_generation"] = bool(data.get("use_ai_generation"))
    if "is_active" in data:
        fields["is_active"] = bool(data.get("is_active"))

    return fields, None


def _announcement_edits(data) -> tuple[dict, dict | None]:
    """Edições do card. Chave ausente ≠ campo apagado — só muda o que veio."""
    edits: dict = {}

    if "body" in data:
        body = str(data.get("body") or "").strip()
        if not body:
            return {}, {"detail": "O texto do announcement não pode ficar vazio.", "field": "body"}
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
    return bool(
        request.headers.get("Idempotency-Key")
        or "base_version" in data
        or "publish_mode" in data
    )


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


def _command_error_response(exc: Exception) -> Response | None:
    from shopman.shop.services.marketing_commands import (
        MarketingCommandConflict,
        MarketingCommandRejected,
    )
    from shopman.shop.services.marketing_contracts import MarketingContractError

    if isinstance(exc, MarketingCommandConflict):
        return Response(exc.as_payload(), status=409)
    if isinstance(exc, MarketingCommandRejected):
        status_code = 404 if exc.code == "announcement_not_found" else 422
        return Response(exc.as_payload(), status=status_code)
    if isinstance(exc, MarketingContractError):
        return Response(exc.as_payload(), status=422)
    return None


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
            "completed_at": (
                receipt.completed_at.isoformat() if receipt.completed_at else ""
            ),
        },
        "announcement": projection_data(
            marketing_projection.build_announcement(result.announcement)
        ),
    }


def _publish_at(raw) -> tuple[object | None, dict | None]:
    """ISO 8601 → datetime aware. Vazio = publicar agora."""
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
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
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
