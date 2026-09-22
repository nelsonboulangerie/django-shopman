"""
Backstage Feed API — Feeds (menuboard/Google/Meta) no Gestor.

Read = board dos canais (venda e exibição) + coleções disponíveis; write = o toggle
"Ativo" de qualquer canal (com período, motivo e gerente) e, nos feeds, as coleções
e a rotação. Gate: ``shop.manage_catalog``.
"""

from __future__ import annotations

from rest_framework.response import Response
from rest_framework.views import APIView

from shopman.backstage.api.permissions import HasBackstagePermission
from shopman.backstage.api.projections import projection_data, read_data
from shopman.backstage.api.telemetry import OperationalObservationMixin
from shopman.backstage.services import feeds as feed_service
from shopman.backstage.services.exceptions import CatalogError


class _FeedBase(OperationalObservationMixin, APIView):
    permission_classes = [HasBackstagePermission]
    required_permission = "shop.manage_catalog"

    def get(self, request):
        from shopman.shop.services.remote_mutations import (
            RemoteMutationInProgress,
            lookup_local_mutation,
            mutation_fingerprint,
        )

        ref = str(request.query_params.get("ref") or "")
        key = str(request.query_params.get("idempotency_key") or "")
        if not ref or not key or len(key) > 128:
            return Response({"detail": "Informe o feed e a intenção."}, status=400)
        scope = mutation_fingerprint({"actor": request.user.pk, "operation": f"feeds.{self.operation}", "ref": ref, "version": 1})
        try:
            result = lookup_local_mutation(scope=scope, key=key)
        except RemoteMutationInProgress:
            result = None
        if result is None:
            return Response({"outcome": "unknown", "intention": key}, status=202)
        return Response({**result.response_body, "replayed": True}, status=result.response_code)

    def mutate(self, request, ref, inputs, execute):
        from shopman.shop.services.remote_mutations import (
            RemoteMutationConflict,
            RemoteMutationInProgress,
            mutation_fingerprint,
            run_idempotent_mutation,
        )

        key = str(request.headers.get("Idempotency-Key") or request.data.get("idempotency_key") or "").strip()
        base = str(request.data.get("base_revision") or "")
        if not key or len(key) > 128 or not base:
            return Response({"detail": "Atualize o feed: a gravação exige intenção e revisão.", "code": "intention_required"}, status=400)
        if request.data.get("expected_actor_id") != request.user.pk:
            return Response({"detail": "A identificação mudou. Atualize o feed antes de gravar.", "code": "actor_changed"}, status=409)
        scope = mutation_fingerprint({"actor": request.user.pk, "operation": f"feeds.{self.operation}", "ref": ref, "version": 1})

        def apply():
            try:
                execute(base)
            except feed_service.FeedConflict as exc:
                return {"detail": str(exc), "outcome": "not_applied", "intention": key}, 409
            except CatalogError as exc:
                return {"detail": str(exc), "outcome": "not_applied", "intention": key}, 400
            return {"ok": True, "ref": ref, "outcome": "applied", "intention": key, **inputs}, 200

        try:
            result = run_idempotent_mutation(scope=scope, key=key,
                fingerprint=mutation_fingerprint({"scope": scope, "base": base, "inputs": inputs}), execute=apply)
        except RemoteMutationConflict as exc:
            return Response({"detail": str(exc), "code": "intention_conflict"}, status=409)
        except RemoteMutationInProgress:
            return Response({"outcome": "in_progress", "intention": key}, status=202)
        return Response({**result.response_body, "replayed": result.replayed}, status=result.response_code)


class FeedBoardView(_FeedBase):
    def get(self, request):
        from shopman.backstage.projections.feeds import build_feed_board

        return Response(read_data(board=projection_data(build_feed_board(user=request.user))))


class FeedSwitchView(_FeedBase):
    """O toggle "Ativo" de qualquer card da aba Canais (venda ou exibição).

    Gerente (``cashman.adjust_shift``, a mesma régua do PDV) só confirma; quem não é
    manda a assinatura de um gerente (crachá ou usuário+PIN) em ``manager_approval``.
    A credencial é conferida aqui e não entra na impressão digital da intenção.
    """

    operation = "switch"

    def post(self, request):
        from datetime import datetime

        from django.utils import timezone

        from shopman.backstage.services.operator import ADJUST_SHIFT
        from shopman.shop.services import channel_switch
        from shopman.shop.services.pos import validate_manager_override
        from shopman.shop.services.pos_intent import PosIntentError

        ref = str(request.data.get("ref") or "").strip()
        is_active = request.data.get("is_active")
        period = str(request.data.get("period") or "").strip()
        reason = str(request.data.get("reason") or "")
        if not ref or not isinstance(is_active, bool) or period not in channel_switch.PERIODS:
            return Response({"detail": "Escolha o canal, o estado e o período."}, status=400)

        def when(field):
            raw = str(request.data.get(field) or "").strip()
            if not raw:
                return None
            try:
                value = datetime.fromisoformat(raw)
            except ValueError:
                return None
            return value if timezone.is_aware(value) else timezone.make_aware(value)

        starts_at, ends_at = when("starts_at"), when("ends_at")
        approver = request.user
        if not request.user.has_perm(ADJUST_SHIFT):
            try:
                approver = validate_manager_override(
                    request.data.get("manager_approval"),
                    operator_username=request.user.get_username(),
                    action="channel_switch",
                    message="Ligar ou desligar um canal pede um gerente.",
                )
            except PosIntentError as exc:
                return Response({"detail": exc.message, "error": exc.as_dict()}, status=exc.status)

        inputs = {
            "is_active": is_active, "period": period, "reason": reason.strip(),
            "starts_at": starts_at.isoformat() if starts_at else "", "ends_at": ends_at.isoformat() if ends_at else "",
        }

        def execute(base):
            try:
                channel_switch.request_switch(
                    ref, is_active, period=period, reason=reason, starts_at=starts_at, ends_at=ends_at,
                    actor=request.user, approved_by=approver, expected_revision=base,
                )
            except channel_switch.ChannelSwitchConflict as exc:
                raise feed_service.FeedConflict(str(exc)) from exc
            except channel_switch.ChannelSwitchError as exc:
                raise CatalogError(str(exc)) from exc

        return self.mutate(request, ref, inputs, execute)


class FeedCollectionsView(_FeedBase):
    operation = "collections"

    def post(self, request):
        ref = str(request.data.get("ref") or "").strip()
        collections = request.data.get("collections")
        if not ref or not isinstance(collections, list):
            return Response({"detail": "ref e collections (lista) são obrigatórios."}, status=400)
        collections = list(dict.fromkeys(str(value).strip() for value in collections if str(value).strip()))
        return self.mutate(request, ref, {"collections": collections},
            lambda base: feed_service.set_collections(ref, collections, expected_revision=base))


class FeedRotationView(_FeedBase):
    operation = "rotation"

    def post(self, request):
        ref = str(request.data.get("ref") or "").strip()
        rotate_seconds = request.data.get("rotate_seconds")
        items_per_page = request.data.get("items_per_page")
        if not ref:
            return Response({"detail": "ref é obrigatório."}, status=400)
        return self.mutate(request, ref, {"rotate_seconds": rotate_seconds, "items_per_page": items_per_page},
            lambda base: feed_service.set_rotation(ref, rotate_seconds=rotate_seconds, items_per_page=items_per_page, expected_revision=base))
