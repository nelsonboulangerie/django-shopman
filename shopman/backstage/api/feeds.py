"""
Backstage Feed API — Feeds (menuboard/Google/Meta) no Gestor.

Read = board dos feeds + coleções disponíveis; write = ligar/pausar e escolher
as coleções que cada feed exibe. Gate: ``shop.manage_catalog``.
"""

from __future__ import annotations

from rest_framework.response import Response
from rest_framework.views import APIView

from shopman.backstage.api.permissions import HasBackstagePermission
from shopman.backstage.api.projections import projection_data
from shopman.backstage.services import feeds as feed_service
from shopman.backstage.services.exceptions import CatalogError


class _FeedBase(APIView):
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

        return Response({"board": projection_data(build_feed_board(user=request.user))})


class FeedActiveView(_FeedBase):
    operation = "active"

    def post(self, request):
        ref = str(request.data.get("ref") or "").strip()
        is_active = request.data.get("is_active")
        if not ref or not isinstance(is_active, bool):
            return Response({"detail": "ref e is_active (bool) são obrigatórios."}, status=400)
        return self.mutate(request, ref, {"is_active": is_active},
            lambda base: feed_service.set_active(ref, is_active, expected_revision=base))


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
