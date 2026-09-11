"""
Backstage Catalog API — matriz produto × superfície (read) + mutações (write).

Contrato consumido pelo Gestor (Nuxt). Read = projection da matriz; write =
pausa/publica/preço por célula e bulk scoped a superfície/coleção/seleção.
Gate: ``shop.manage_catalog``. Mutações delegam ao facade
``backstage.services.catalog`` (que dispara o auto-trigger / reconcilia).
"""

from __future__ import annotations

from django.core.exceptions import ValidationError
from drf_spectacular.utils import OpenApiResponse, extend_schema, extend_schema_view
from rest_framework.response import Response
from rest_framework.views import APIView

from shopman.backstage.api.permissions import HasBackstagePermission
from shopman.backstage.api.projections import projection_data
from shopman.backstage.parsing import as_int
from shopman.backstage.services import catalog as catalog_service
from shopman.backstage.services.exceptions import (
    AiAssistError,
    AiAssistNotConfigured,
    CatalogError,
)


def _actor(request) -> str:
    """Quem agiu = quem está logado. A segunda identidade deixou de existir (D1-B)."""
    user = getattr(request, "user", None)
    return getattr(user, "username", None) or "operator"


class _CatalogBase(APIView):
    permission_classes = [HasBackstagePermission]
    required_permission = "shop.manage_catalog"


@extend_schema_view(
    get=extend_schema(
        tags=["backstage"],
        summary="Catalog matrix (produto × superfície)",
        responses={200: OpenApiResponse(description="Matriz de catálogo por superfície.")},
    ),
)
class CatalogMatrixView(_CatalogBase):
    def get(self, request):
        from shopman.backstage.projections.catalog import build_catalog_matrix, curation_actions

        collection_ref = (request.query_params.get("collection") or "").strip()
        matrix = build_catalog_matrix(collection_ref, user=request.user)
        return Response({"matrix": projection_data(matrix), "collection_ref": collection_ref,
            "actions": [projection_data(action) for action in curation_actions(collection_ref, request.user)]})


class CatalogCellView(_CatalogBase):
    """One intended cell patch, with independent revisions and a local receipt."""

    def _scope(self, request, ref):
        from shopman.shop.services.remote_mutations import mutation_fingerprint

        return mutation_fingerprint({"operation": "catalog.cell", "actor": request.user.pk, "ref": ref})

    def get(self, request):
        from shopman.shop.services.remote_mutations import RemoteMutationInProgress, lookup_local_mutation

        key, ref = request.query_params.get("idempotency_key"), request.query_params.get("ref")
        if not key or not ref:
            return Response({"detail": "Informe a intenção e o recurso."}, status=400)
        try:
            result = lookup_local_mutation(scope=self._scope(request, ref), key=key)
            if result is None:
                return Response({"outcome": "unknown"}, status=202)
            return Response(result.response_body, status=result.response_code)
        except RemoteMutationInProgress:
            return Response({"outcome": "in_progress"}, status=202)

    def post(self, request):
        from shopman.backstage.services.exceptions import CatalogConflict
        from shopman.shop.services.remote_mutations import (
            RemoteMutationConflict,
            RemoteMutationInProgress,
            mutation_fingerprint,
            run_idempotent_mutation,
        )

        data = request.data
        if not isinstance(data, dict):
            return Response({"detail": "Informe os campos da célula."}, status=400)
        sku, surface_ref = data.get("sku"), data.get("surface_ref")
        key = request.headers.get("Idempotency-Key")
        revisions, base = data.get("base_revisions"), data.get("base_revision")
        if not all(isinstance(value, str) and value for value in (sku, surface_ref, key, base)) or len(key) > 128 or not isinstance(revisions, dict):
            return Response({"detail": "Atualize a célula: a gravação exige intenção e revisão."}, status=400)
        if data.get("expected_actor_id") != request.user.pk:
            return Response({"detail": "A identificação mudou. Confira a célula."}, status=409)
        patch = {field: data[field] for field in ("is_published", "is_sellable", "price_q") if field in data}
        if "price_q" in patch:
            patch["price_q"] = as_int(data, "price_q", default=None)
        ref = mutation_fingerprint({"sku": sku, "surface": surface_ref})
        scope = self._scope(request, ref)

        def execute():
            try:
                item = catalog_service.set_cell(sku, surface_ref, **patch, actor=_actor(request), expected_revisions=revisions)
            except CatalogConflict as exc:
                return {"outcome": "not_applied", "detail": str(exc), "current": getattr(exc, "current", {}), "conflicting_fields": getattr(exc, "fields", [])}, 409
            except (CatalogError, ValidationError) as exc:
                return {"outcome": "not_applied", "detail": str(exc)}, 400
            return {"ok": True, "outcome": "applied", "intention": key, "sku": sku, "surface_ref": surface_ref,
                "is_published": item.is_published, "is_sellable": item.is_sellable, "price_q": item.price_q}, 200

        try:
            result = run_idempotent_mutation(scope=scope, key=key,
                fingerprint=mutation_fingerprint({"scope": scope, "base": base, "revisions": revisions, "patch": patch}), execute=execute)
            return Response(result.response_body, status=result.response_code)
        except RemoteMutationConflict:
            return Response({"detail": "Esta intenção já representa outra edição.", "code": "intention_conflict"}, status=409)
        except RemoteMutationInProgress:
            return Response({"outcome": "in_progress"}, status=202)


class CatalogProductDetailView(_CatalogBase):
    """Partial product edits have leaf revisions and an atomic local receipt."""

    def _scope(self, request, sku):
        from shopman.shop.services.remote_mutations import mutation_fingerprint

        return mutation_fingerprint({"version": 1, "actor": request.user.pk, "operation": "catalog.product-detail", "sku": sku})

    def _read(self, request, sku):
        from shopman.backstage.projections.catalog import product_detail_action

        product = catalog_service.get_product_detail(sku)
        return {"product": product, "action": projection_data(product_detail_action(sku, product, request.user))}

    def get(self, request, sku: str):
        from shopman.shop.services.remote_mutations import RemoteMutationInProgress, lookup_local_mutation

        try:
            key = request.query_params.get("idempotency_key")
            if not key:
                return Response(self._read(request, sku))
            # A receipt is a committed fact, independent of a later projection
            # outage or product removal. This GET must never re-run that read.
            receipt = lookup_local_mutation(scope=self._scope(request, sku), key=key)
            if receipt is None:
                return Response({"outcome": "unknown"}, status=202)
            return Response(receipt.response_body, status=receipt.response_code)
        except RemoteMutationInProgress:
            return Response({"outcome": "in_progress"}, status=202)
        except (CatalogError, ValidationError) as exc:
            return Response({"detail": str(exc)}, status=404)

    def patch(self, request, sku: str):
        from shopman.backstage.services.exceptions import CatalogConflict
        from shopman.shop.services.remote_mutations import (
            RemoteMutationConflict,
            RemoteMutationInProgress,
            mutation_fingerprint,
            run_idempotent_mutation,
        )

        data = request.data
        key = request.headers.get("Idempotency-Key") or data.get("idempotency_key")
        patch = data.get("patch")
        revisions = data.get("base_revisions")
        if not isinstance(key, str) or not key or len(key) > 128 or not isinstance(patch, dict) or not isinstance(revisions, dict) or not data.get("base_revision"):
            return Response({"detail": "Atualize o produto: a gravação exige intenção e revisão.", "code": "intention_required"}, status=400)
        if data.get("expected_actor_id") != request.user.pk:
            return Response({"detail": "A identificação mudou. Confira o produto.", "code": "actor_changed"}, status=409)
        scope = self._scope(request, sku)
        fingerprint = mutation_fingerprint({"scope": scope, "patch": patch, "revisions": revisions, "base": data["base_revision"]})

        def execute():
            try:
                catalog_service.update_product_detail(sku, patch, actor=_actor(request), expected_revisions=revisions)
            except CatalogConflict as exc:
                return {"outcome": "not_applied", "detail": str(exc), "conflicting_fields": getattr(exc, "fields", [])}, 409
            except (CatalogError, ValidationError) as exc:
                return {"outcome": "not_applied", "detail": str(exc)}, 400
            return {"ok": True, "outcome": "applied", "intention": key, "sku": sku, "changed_fields": list(patch)}, 200

        try:
            result = run_idempotent_mutation(scope=scope, key=key, fingerprint=fingerprint, execute=execute)
            return Response({**result.response_body, "replayed": result.replayed, **self._read(request, sku)}, status=result.response_code)
        except RemoteMutationConflict:
            return Response({"detail": "Esta intenção já representa outra edição.", "code": "intention_conflict"}, status=409)
        except RemoteMutationInProgress:
            return Response({"outcome": "in_progress"}, status=202)
        except (CatalogError, ValidationError) as exc:
            return Response({"detail": str(exc)}, status=404)


class CatalogProductView(CatalogProductDetailView):
    """Global switches reuse the product editor's atomic writer and receipt."""

    http_method_names = ["get", "post", "head", "options"]

    def get(self, request):
        sku = request.query_params.get("ref")
        if not isinstance(sku, str) or not sku:
            return Response({"detail": "Informe o produto da intenção."}, status=400)
        return super().get(request, sku)

    def post(self, request):
        data = request.data
        if not isinstance(data, dict):
            return Response({"detail": "Informe os campos do produto."}, status=400)
        sku, patch = data.get("sku"), data.get("patch")
        if not isinstance(sku, str) or not sku or not isinstance(patch, dict) or not patch or set(patch) - {"is_published", "is_sellable"} or any(value is None for value in patch.values()):
            return Response({"detail": "Atualize o catálogo e confirme a disponibilidade do produto."}, status=400)
        return super().patch(request, sku)


class CatalogAiAssistView(_CatalogBase):
    """Sugere o conteúdo de UM campo de texto de um produto (assist de IA).

    Por campo, nunca em lote: o operador pede a sugestão de um campo e aceita ou
    descarta ela sozinha na superfície. Não grava nada — quem persiste é o PATCH
    do produto (ou o POST social), depois do "Aceitar".

    503 quando o deployment não tem ``AI_ASSIST_API_KEY``: a superfície mostra um
    aviso, não um erro. O assist é conveniência, não caminho crítico.
    """

    def post(self, request):
        sku = (request.data.get("sku") or "").strip()
        field = (request.data.get("field") or "").strip()
        if not sku or not field:
            return Response({"detail": "sku e field são obrigatórios."}, status=400)

        try:
            suggestion = catalog_service.ai_assist_field(
                sku, field, current_value=str(request.data.get("current_value") or "")
            )
        except AiAssistNotConfigured as exc:
            return Response({"detail": str(exc)}, status=503)
        except AiAssistError as exc:
            return Response({"detail": str(exc)}, status=502)
        except (CatalogError, ValidationError) as exc:
            return Response({"detail": str(exc)}, status=400)

        return Response({"suggestion": suggestion})


class CatalogBulkView(_CatalogBase):
    """Bulk pausa/publica scoped a superfície + (coleção | seleção de skus)."""

    def post(self, request):
        surface_ref = (request.data.get("surface_ref") or "").strip()
        if not surface_ref:
            return Response({"detail": "surface_ref é obrigatório."}, status=400)

        is_published = request.data.get("is_published")
        is_sellable = request.data.get("is_sellable")
        if is_published is None and is_sellable is None:
            return Response(
                {"detail": "Informe is_published e/ou is_sellable."}, status=400
            )

        collection_ref = (request.data.get("collection_ref") or "").strip()
        skus = request.data.get("skus") or []

        try:
            if collection_ref:
                count = catalog_service.bulk_set_collection(
                    collection_ref,
                    surface_ref,
                    is_published=is_published,
                    is_sellable=is_sellable,
                    actor=_actor(request),
                )
            elif isinstance(skus, list) and skus:
                count = catalog_service.bulk_set(
                    [str(s).strip() for s in skus],
                    surface_ref,
                    is_published=is_published,
                    is_sellable=is_sellable,
                    actor=_actor(request),
                )
            else:
                return Response(
                    {"detail": "Informe collection_ref ou uma lista skus."}, status=400
                )
        except (CatalogError, ValidationError) as exc:
            return Response({"detail": str(exc)}, status=400)

        return Response({"ok": True, "surface_ref": surface_ref, "count": count})


class CatalogBulkPriceView(_CatalogBase):
    """Exact preview and atomic local receipt; remote sync is independently recoverable."""

    @staticmethod
    def _scope(request):
        from shopman.shop.services.remote_mutations import mutation_fingerprint

        return mutation_fingerprint({"version": 1, "actor": request.user.pk, "operation": "catalog.bulk-price"})

    def get(self, request):
        from shopman.shop.services.remote_mutations import RemoteMutationInProgress, lookup_local_mutation

        key = str(request.query_params.get("idempotency_key") or "")
        if not key:
            return Response({"detail": "Informe a intenção."}, status=400)
        try:
            receipt = lookup_local_mutation(scope=self._scope(request), key=key)
        except RemoteMutationInProgress:
            receipt = None
        if receipt is None:
            return Response({"outcome": "unknown", "detail": "Resultado ainda não confirmado."}, status=202)
        return Response(receipt.response_body, status=receipt.response_code)

    def post(self, request):
        from shopman.backstage.services.exceptions import CatalogConflict
        from shopman.shop.services.remote_mutations import (
            RemoteMutationConflict,
            RemoteMutationInProgress,
            mutation_fingerprint,
            run_idempotent_mutation,
        )

        data = dict(request.data)
        try:
            if data.get("preview") is True:
                return Response({"preview": catalog_service.preview_bulk_price(data, actor_id=request.user.pk)})
            key = request.headers.get("Idempotency-Key") or data.get("idempotency_key")
            if not isinstance(key, str) or not key or len(key) > 128 or not data.get("base_revision"):
                return Response({"detail": "Atualize o Gestor e revise a prévia antes de confirmar.", "error": {"code": "intention_required"}}, status=400)
            if data.get("expected_actor_id") != request.user.pk:
                return Response({"detail": "A identificação mudou. Revise a prévia.", "error": {"code": "actor_changed"}}, status=409)
            scope = self._scope(request)
            payload = {key: value for key, value in data.items() if key not in {"idempotency_key", "preview"}}

            def execute():
                try:
                    return catalog_service.apply_bulk_price_intention(payload, actor_id=request.user.pk), 200
                except CatalogConflict as exc:
                    return {"outcome": "not_applied", "detail": str(exc), "error": {"code": "catalog_changed"}}, 409
                except (CatalogError, ValidationError) as exc:
                    return {"outcome": "not_applied", "detail": str(exc)}, 400

            result = run_idempotent_mutation(
                scope=scope, key=key, fingerprint=mutation_fingerprint({"scope": scope, "payload": payload}), execute=execute,
            )
            return Response(result.response_body, status=result.response_code)
        except (CatalogError, ValidationError) as exc:
            return Response({"detail": str(exc)}, status=400)
        except RemoteMutationConflict:
            return Response({"detail": "Esta intenção já representa outra alteração.", "error": {"code": "intention_conflict"}}, status=409)
        except RemoteMutationInProgress:
            return Response({"outcome": "unknown", "detail": "Alteração em processamento; consulte esta intenção."}, status=202)


class _CatalogReorderView(_CatalogBase):
    operation = ""
    field = ""

    def _scope(self, request, ref):
        from shopman.shop.services.remote_mutations import mutation_fingerprint

        return mutation_fingerprint({"actor": request.user.pk, "operation": self.operation, "ref": ref})

    def get(self, request):
        from shopman.shop.services.remote_mutations import RemoteMutationInProgress, lookup_local_mutation

        key = request.query_params.get("idempotency_key")
        ref = request.query_params.get("ref", "")
        if not key:
            return Response({"detail": "Informe a intenção para consultar."}, status=400)
        try:
            result = lookup_local_mutation(scope=self._scope(request, ref), key=key)
            if result is None:
                return Response({"outcome": "unknown"}, status=202)
            return Response(result.response_body, status=result.response_code)
        except RemoteMutationInProgress:
            return Response({"outcome": "in_progress"}, status=202)

    def post(self, request):
        from shopman.backstage.services.exceptions import CatalogConflict
        from shopman.shop.services.remote_mutations import (
            RemoteMutationConflict,
            RemoteMutationInProgress,
            mutation_fingerprint,
            run_idempotent_mutation,
        )

        data = request.data
        key = request.headers.get("Idempotency-Key")
        ref = data.get("ref", "")
        ordered = data.get(self.field)
        base = data.get("base_revision")
        if not isinstance(key, str) or not key or len(key) > 128 or not isinstance(base, str) or not base:
            return Response({"detail": "Atualize o catálogo: a ordenação exige intenção e revisão."}, status=400)
        if not isinstance(ref, str) or not isinstance(ordered, list) or not ordered or any(not isinstance(value, str) for value in ordered):
            return Response({"detail": "Informe a coleção e a lista completa de referências."}, status=400)
        if (self.operation == "reorder-items" and not ref) or (self.operation == "reorder-collections" and ref):
            return Response({"detail": "O recurso não corresponde à ordenação."}, status=400)
        if data.get("expected_actor_id") != request.user.pk:
            return Response({"detail": "A identificação mudou. Confira a ordem."}, status=409)
        scope = self._scope(request, ref)

        def execute():
            try:
                if self.operation == "reorder-items":
                    count = catalog_service.reorder_collection_items(ref, ordered, actor=_actor(request), expected_revision=base)
                else:
                    count = catalog_service.reorder_collections(ordered, actor=_actor(request), expected_revision=base)
            except CatalogConflict as exc:
                return {"outcome": "not_applied", "detail": str(exc)}, 409
            except (CatalogError, ValidationError) as exc:
                return {"outcome": "not_applied", "detail": str(exc)}, 400
            return {"ok": True, "outcome": "applied", "count": count}, 200

        try:
            result = run_idempotent_mutation(scope=scope, key=key,
                fingerprint=mutation_fingerprint({"scope": scope, "base": base, "ordered": ordered}), execute=execute)
            return Response(result.response_body, status=result.response_code)
        except RemoteMutationConflict:
            return Response({"detail": "Esta intenção já representa outra ordem.", "code": "intention_conflict"}, status=409)
        except RemoteMutationInProgress:
            return Response({"outcome": "in_progress"}, status=202)


class CatalogReorderCollectionsView(_CatalogReorderView):
    operation = "reorder-collections"
    field = "ordered_refs"


class CatalogReorderItemsView(_CatalogReorderView):
    operation = "reorder-items"
    field = "ordered_skus"


class CatalogSyncStatusView(_CatalogBase):
    """Estado de sync por produto × plataforma (para o selo de cada célula)."""

    def get(self, request):
        from shopman.shop.services.catalog_sync import sync_status_map

        channel_ref = (request.query_params.get("channel_ref") or "").strip() or None
        skus_param = (request.query_params.get("sku") or "").strip()
        skus = [s for s in (part.strip() for part in skus_param.split(",")) if s] or None
        return Response({"sync_status": sync_status_map(skus, channel_ref=channel_ref)})


class CatalogSocialView(_CatalogBase):
    """Lê/salva os atributos PIM sociais (Product.metadata['social']) de um SKU.

    O painel PIM da matriz edita marca/GTIN/categoria/hashtags e salva aqui. A
    escrita valida via ``ProductSocialAttributes.errors()`` e persiste com
    ``set_social_attributes`` (só chaves não-default) — sem migração (padrão
    fiscal/nutrition). Salvar re-projeta via o gatilho de ``Product.save``.
    """

    def get(self, request):
        from shopman.offerman import get_social_attributes
        from shopman.offerman.models import Product

        sku = (request.query_params.get("sku") or "").strip()
        if not sku:
            return Response({"detail": "sku é obrigatório."}, status=400)
        product = Product.objects.filter(sku=sku).first()
        if product is None:
            return Response({"detail": "Produto não encontrado."}, status=404)
        return Response({"sku": sku, "social": _social_payload(get_social_attributes(product))})

    def post(self, request):
        from shopman.offerman import (
            ProductSocialAttributes,
            get_social_attributes,
            set_social_attributes,
        )
        from shopman.offerman.models import Product

        sku = (request.data.get("sku") or "").strip()
        if not sku:
            return Response({"detail": "sku é obrigatório."}, status=400)
        product = Product.objects.filter(sku=sku).first()
        if product is None:
            return Response({"detail": "Produto não encontrado."}, status=404)

        current = get_social_attributes(product)
        data = request.data
        # Merge parcial: campo ausente no corpo mantém o valor atual.
        attrs = ProductSocialAttributes(
            brand=_field(data, "brand", current.brand),
            gtin=_field(data, "gtin", current.gtin),
            mpn=_field(data, "mpn", current.mpn),
            condition=_field(data, "condition", current.condition),
            google_product_category=_field(
                data, "google_product_category", current.google_product_category
            ),
            tiktok_category_id=_field(data, "tiktok_category_id", current.tiktok_category_id),
            hashtags=data["hashtags"] if "hashtags" in data else list(current.hashtags),
            social_caption=_field(data, "social_caption", current.social_caption),
        )
        problems = attrs.errors()
        if problems:
            return Response({"detail": problems[0], "errors": problems}, status=400)

        product.metadata = set_social_attributes(product.metadata, attrs)
        product.save(update_fields=["metadata"])
        return Response({"ok": True, "sku": sku, "social": _social_payload(attrs)})


class CatalogResyncView(_CatalogBase):
    """Re-enfileira a projeção de um SKU (uma plataforma ou todas as configuradas)."""

    def post(self, request):
        sku = (request.data.get("sku") or "").strip()
        channel_ref = (request.data.get("channel_ref") or "").strip()
        if not sku:
            return Response({"detail": "sku é obrigatório."}, status=400)

        from shopman.offerman.conf import get_projection_backend_channels

        from shopman.shop.handlers.catalog_projection import enqueue_project

        targets = [channel_ref] if channel_ref else list(get_projection_backend_channels())
        for listing_ref in targets:
            enqueue_project(sku, listing_ref, trigger="manual_resync")
        return Response({"ok": True, "sku": sku, "channels": targets})


def _field(data, key: str, current: str) -> str:
    """Valor textual do corpo (aparado) ou o atual quando a chave está ausente."""
    if key not in data:
        return current
    return str(data.get(key) or "").strip()


def _social_payload(attrs) -> dict:
    return {
        "brand": attrs.brand,
        "gtin": attrs.gtin,
        "mpn": attrs.mpn,
        "condition": attrs.condition,
        "google_product_category": attrs.google_product_category,
        "tiktok_category_id": attrs.tiktok_category_id,
        "hashtags": list(attrs.hashtags),
        "social_caption": attrs.social_caption,
        "has_data": attrs.has_data,
    }

