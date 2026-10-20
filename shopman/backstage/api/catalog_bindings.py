"""API de revisão e vínculos locais com intenção recuperável e auditoria atômica."""

import hashlib

from django.conf import settings
from rest_framework.response import Response
from rest_framework.views import APIView

from shopman.backstage.api.permissions import HasBackstagePermission
from shopman.backstage.api.projections import projection_data, read_data
from shopman.backstage.api.telemetry import OperationalObservationMixin
from shopman.backstage.projections.catalog_bindings import build_catalog_binding_review
from shopman.backstage.services import catalog_bindings as service
from shopman.shop.adapters.catalog_projection_ifood import IFoodCatalogWriteBlocked, IFoodRateLimitError
from shopman.shop.models import CatalogSnapshot
from shopman.shop.observability import ServerTimingMixin
from shopman.shop.services import ifood_catalog_categories as category_service
from shopman.shop.services.remote_mutations import (
    RemoteMutationConflict,
    RemoteMutationInProgress,
    lookup_local_mutation,
    mutation_fingerprint,
    run_idempotent_mutation,
)


def _error(detail, field="", **extra):
    return {"detail": detail, "field": field, "errors": {field: [detail]} if field else {}, **extra}


def _scope(user, ref, operation):
    return mutation_fingerprint({"actor": user.pk, "channel": ref, "operation": operation, "version": 1})


class _Base(ServerTimingMixin, OperationalObservationMixin, APIView):
    permission_classes = [HasBackstagePermission]
    required_permission = "shop.manage_catalog"

    def get(self, request, ref):
        key = request.query_params.get("idempotency_key")
        if not isinstance(key, str) or not key.strip() or len(key) > 128:
            return Response(_error("Informe a intenção para consultar o recibo.", "idempotency_key"), status=400)
        try:
            result = lookup_local_mutation(scope=_scope(request.user, ref, self.operation), key=key.strip())
        except RemoteMutationInProgress:
            result = None
        except RemoteMutationConflict:
            return Response(_error("Esta intenção pertence a outro contrato."), status=409)
        if result is None:
            return Response({"outcome": "unknown", "intention": key}, status=202)
        return Response({**result.response_body, "replayed": True}, status=result.response_code)

    def mutate(self, request, ref, inputs, execute):
        keys = [value for value in (request.headers.get("Idempotency-Key"), request.data.get("idempotency_key")) if value is not None]
        if not keys or any(not isinstance(value, str) or not value.strip() or len(value) > 128 for value in keys):
            return Response(_error("A gravação exige uma intenção válida.", "idempotency_key"), status=400)
        if len({value.strip() for value in keys}) != 1:
            return Response(_error("As chaves da intenção divergem.", "idempotency_key"), status=409)
        key = keys[0].strip()
        expected_actor = request.data.get("expected_actor_id")
        if type(expected_actor) is not int or expected_actor != request.user.pk:
            return Response(_error("A identificação mudou. Atualize antes de gravar.", "expected_actor_id"), status=409)
        scope = _scope(request.user, ref, self.operation)

        def apply():
            try:
                output = execute()
            except IFoodRateLimitError as exc:
                return _error(
                    "O iFood pediu uma pausa. A intenção foi preservada para tentar novamente.",
                    outcome="not_applied",
                    intention=key,
                    retry_after=exc.retry_after,
                ), 429
            except IFoodCatalogWriteBlocked as exc:
                return _error(str(exc), outcome="not_applied", intention=key), 400
            except service.CatalogBindingConflict as exc:
                return _error(str(exc), outcome="not_applied", intention=key), 409
            except service.CatalogBindingError as exc:
                return _error(str(exc), outcome="not_applied", intention=key), 400
            return {"ok": True, "outcome": "applied", "intention": key, **output}, 200

        try:
            result = run_idempotent_mutation(scope=scope, key=key,
                fingerprint=mutation_fingerprint({"scope": scope, "inputs": inputs}), execute=apply)
        except RemoteMutationConflict:
            return Response(_error("Esta intenção já foi usada para outra escolha.", "idempotency_key"), status=409)
        except RemoteMutationInProgress:
            return Response({"outcome": "in_progress", "intention": key}, status=202)
        return Response({**result.response_body, "replayed": result.replayed}, status=result.response_code)


class CatalogBindingReviewView(_Base):
    def get(self, request, ref):
        snapshot_id = request.query_params.get("snapshot_id")
        if snapshot_id is not None:
            try:
                snapshot_id = int(snapshot_id)
                if snapshot_id < 1:
                    raise ValueError
            except (TypeError, ValueError):
                return Response(_error("Snapshot inválido.", "snapshot_id"), status=400)
        try:
            board = build_catalog_binding_review(
                channel_ref=ref,
                snapshot_id=snapshot_id,
                user=request.user,
                category_reader=category_service.list_categories,
            )
        except service.CatalogBindingError as exc:
            return Response(_error(str(exc)), status=400)
        return Response(read_data(board=projection_data(board)))


class CatalogSnapshotImportView(_Base):
    operation = "catalog.snapshot.import"

    def post(self, request, ref):
        if not isinstance(request.data, dict):
            return Response(_error("Informe um objeto JSON."), status=400)
        raw = request.data.get("raw_json")
        base = request.data.get("base_revision")
        if not isinstance(base, str) or len(base) != 64:
            return Response(_error("Atualize o canal: a importação exige revisão.", "base_revision"), status=400)
        try:
            if not isinstance(raw, str) or len(raw.encode("utf-8")) > service.MAX_SNAPSHOT_BYTES:
                raise ValueError
            digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        except (ValueError, UnicodeError):
            return Response(_error("Informe JSON original de até 20 MiB.", "raw_json"), status=400)

        def execute():
            snapshot = service.import_snapshot(channel_ref=ref, raw_json=raw, actor=request.user, expected_revision=base)
            return {"snapshot_id": snapshot.pk}

        return self.mutate(request, ref, {"raw_sha256": digest, "base_revision": base}, execute)


class CatalogBindingConfirmView(_Base):
    operation = "catalog.binding.confirm"

    def post(self, request, ref):
        if not isinstance(request.data, dict):
            return Response(_error("Informe um objeto JSON."), status=400)
        data = request.data
        snapshot_id, item_id, sku, base = (data.get(key) for key in ("snapshot_id", "item_id", "sku", "base_revision"))
        if type(snapshot_id) is not int or snapshot_id < 1:
            return Response(_error("Snapshot inválido.", "snapshot_id"), status=400)
        if any(not isinstance(value, str) or not value.strip() for value in (item_id, sku, base)):
            return Response(_error("Item, SKU e revisão são obrigatórios."), status=400)
        if len(item_id) > 256 or len(sku) > 100 or len(base) != 64:
            return Response(_error("Item, SKU ou revisão fora do formato aceito."), status=400)

        def execute():
            _, revision = service.bind_item(channel_ref=ref, snapshot_id=snapshot_id, item_id=item_id,
                sku=sku, base_revision=base, actor=request.user)
            return {"snapshot_id": snapshot_id, "item_id": item_id, "sku": sku, "revision": revision}

        return self.mutate(request, ref,
            {"snapshot_id": snapshot_id, "item_id": item_id, "sku": sku, "base_revision": base}, execute)


def _remote_category(rows, category_ref):
    if isinstance(rows, dict):
        rows = rows.get("categories")
    if not isinstance(rows, list):
        raise service.CatalogBindingError("O iFood não devolveu uma lista de categorias válida.")
    return next((row for row in rows if isinstance(row, dict) and row.get("id") == category_ref), None)


class CatalogCategoryView(_Base):
    operation = "catalog.category.change"

    def post(self, request, ref):
        if not isinstance(request.data, dict):
            return Response(_error("Informe os campos da categoria."), status=400)
        data = request.data
        action = data.get("action")
        snapshot_id = data.get("snapshot_id")
        catalog_ref = data.get("catalog_ref")
        category_ref = data.get("category_ref")
        if action not in {"map", "rename", "reorder"}:
            return Response(_error("Escolha mapear, renomear ou reordenar.", "action"), status=400)
        if isinstance(snapshot_id, bool) or not isinstance(snapshot_id, int) or snapshot_id < 1:
            return Response(_error("Captura inválida. Atualize a página.", "snapshot_id"), status=400)
        if not isinstance(catalog_ref, str) or not catalog_ref.strip() or len(catalog_ref) > 128:
            return Response(_error("Catálogo inválido. Atualize a página.", "catalog_ref"), status=400)
        if not isinstance(category_ref, str) or not category_ref.strip() or len(category_ref) > 256:
            return Response(_error("Escolha uma categoria válida.", "category_ref"), status=400)
        catalog_ref, category_ref = catalog_ref.strip(), category_ref.strip()
        account_ref = (getattr(settings, "SHOPMAN_IFOOD", {}) or {}).get("merchant_id")
        if not isinstance(account_ref, str) or not CatalogSnapshot.objects.filter(
            pk=snapshot_id,
            channel__ref=ref,
            provider="ifood",
            account_ref=account_ref,
            catalog_ref=catalog_ref,
        ).exists():
            return Response(_error("A captura não corresponde à loja iFood configurada."), status=409)

        def execute():
            try:
                if action == "rename":
                    name = data.get("name")
                    if not isinstance(name, str) or not name.strip() or len(name.strip()) > 128:
                        raise service.CatalogBindingError("Informe um nome de até 128 caracteres.")
                    name = name.strip()
                    category_service.rename_category(channel_ref=ref, catalog_ref=catalog_ref,
                        category_ref=category_ref, name=name)
                    rows = category_service.list_categories(channel_ref=ref, catalog_ref=catalog_ref)
                    category = _remote_category(rows, category_ref)
                    if category is None or category.get("name") != name:
                        raise service.CatalogBindingError("O iFood não confirmou o novo nome da categoria.")
                    return {"action": action, "category": category}
                if action == "reorder":
                    index = data.get("index")
                    if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index <= 9999:
                        raise service.CatalogBindingError("Informe uma posição entre 0 e 9999.")
                    category_service.reorder_category(channel_ref=ref, catalog_ref=catalog_ref,
                        category_ref=category_ref, index=index)
                    rows = category_service.list_categories(channel_ref=ref, catalog_ref=catalog_ref)
                    category = _remote_category(rows, category_ref)
                    if category is None or category.get("index") != index:
                        raise service.CatalogBindingError("O iFood não confirmou a nova posição da categoria.")
                    return {"action": action, "category": category}
                collection_ref = data.get("collection_ref")
                if not isinstance(collection_ref, str) or not collection_ref.strip() or len(collection_ref) > 50:
                    raise service.CatalogBindingError("Escolha uma coleção válida.")
                rows = category_service.list_categories(channel_ref=ref, catalog_ref=catalog_ref)
                category = _remote_category(rows, category_ref)
                if category is None:
                    raise service.CatalogBindingError("A categoria escolhida não foi confirmada no iFood.")
                category_service.set_collection_category(channel_ref=ref,
                    collection_ref=collection_ref.strip(), category_ref=category_ref)
                return {"action": action, "collection_ref": collection_ref.strip(), "category": category}
            except category_service.IFoodCategoryConflict as exc:
                raise service.CatalogBindingConflict(str(exc)) from exc
            except category_service.IFoodCategoryOperationError as exc:
                raise service.CatalogBindingError(str(exc)) from exc

        inputs = {key: data.get(key) for key in ("action", "snapshot_id", "catalog_ref", "category_ref", "collection_ref", "name", "index")}
        return self.mutate(request, ref, inputs, execute)
