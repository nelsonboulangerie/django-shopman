"""API de revisão e vínculos locais com intenção recuperável e auditoria atômica."""

import hashlib

from rest_framework.response import Response
from rest_framework.views import APIView

from shopman.backstage.api.permissions import HasBackstagePermission
from shopman.backstage.api.projections import projection_data, read_data
from shopman.backstage.api.telemetry import OperationalObservationMixin
from shopman.backstage.projections.catalog_bindings import build_catalog_binding_review
from shopman.backstage.services import catalog_bindings as service
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


class _Base(OperationalObservationMixin, APIView):
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
            board = build_catalog_binding_review(channel_ref=ref, snapshot_id=snapshot_id, user=request.user)
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
