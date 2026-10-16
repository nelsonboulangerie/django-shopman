"""Backstage Customers API — a seção Clientes do Gestor.

Achar o cadastro (inclusive o ``IF-*`` sem telefone que ninguém digitou),
ler a ficha, ver a PRÉVIA da unificação lado a lado, unificar e desfazer
dentro da janela. Gate único: ``shop.manage_customers`` — a mesma permissão
que governa criar, editar e desfazer unificação no Admin.

Leitura = projections de ``shopman.backstage.projections.customers``;
escrita = ``shopman.backstage.services.customers``, que só traduz o pedido
para o ``MergeService`` do Guestman.
"""

from __future__ import annotations

from drf_spectacular.utils import OpenApiResponse, extend_schema, extend_schema_view
from rest_framework.response import Response
from rest_framework.views import APIView

from shopman.backstage.api.permissions import HasBackstagePermission
from shopman.backstage.api.projections import projection_data, read_data
from shopman.backstage.api.telemetry import OperationalObservationMixin
from shopman.backstage.parsing import as_int
from shopman.backstage.services import customers as customers_service
from shopman.backstage.services.exceptions import CustomerMergeError, CustomerMutationError, CustomerNotFound
from shopman.shop.services.remote_mutations import (
    RemoteMutationConflict,
    RemoteMutationInProgress,
    mutation_fingerprint,
    run_idempotent_mutation,
)


def _actor(request) -> str:
    user = getattr(request, "user", None)
    return getattr(user, "username", None) or "gestor"


def _refusal(exc: CustomerMergeError) -> Response:
    status = 404 if isinstance(exc, CustomerNotFound) else 422
    return Response({"detail": str(exc)}, status=status)


def _mutation_refusal(exc: CustomerMutationError) -> Response:
    status = 409 if exc.code in {"customer_changed", "contact_conflict", "inactive"} else 400
    payload = {"detail": exc.detail, "error": {"code": exc.code}}
    if exc.field:
        payload["field"] = exc.field
        payload["errors"] = {exc.field: [exc.detail]}
    return Response(payload, status=status)


class _CustomersBase(OperationalObservationMixin, APIView):
    permission_classes = [HasBackstagePermission]
    required_permission = "shop.manage_customers"


@extend_schema_view(
    get=extend_schema(
        tags=["backstage"],
        summary="Customer list (search + filters, paginated)",
        responses={200: OpenApiResponse(description="Página de clientes ativos.")},
    ),
    post=extend_schema(
        tags=["backstage"],
        summary="Create a customer with an idempotent intention",
        responses={201: OpenApiResponse(description="Cadastro criado e projetado.")},
    ),
)
class CustomerListView(_CustomersBase):
    def get(self, request):
        from shopman.backstage.projections.customers import build_customer_list

        sort = request.query_params.get("sort") or "recent"
        if sort not in {"recent", "name"}:
            return Response(
                {"detail": "Ordenação desconhecida.", "field": "sort", "errors": {"sort": ["Ordenação desconhecida."]}},
                status=400,
            )
        listing = build_customer_list(
            query=request.query_params.get("q") or "",
            filter_ref=request.query_params.get("filter") or "all",
            page=as_int(request.query_params.dict(), "page", default=1, min_value=1),
            sort=sort,
        )
        return Response(read_data(list=projection_data(listing)))

    def post(self, request):
        from shopman.backstage.projections.customers import build_customer_detail

        data = dict(request.data or {})
        key = request.headers.get("Idempotency-Key") or data.pop("idempotencyKey", None)
        if not isinstance(key, str) or not key or len(key) > 128:
            return Response(
                {"detail": "Atualize a lista e tente novamente.", "error": {"code": "intention_required"}},
                status=400,
            )
        scope = mutation_fingerprint({"version": 1, "actor": request.user.pk, "operation": "customer-create"})
        fingerprint = mutation_fingerprint({"scope": scope, "payload": data})

        def execute():
            try:
                customer = customers_service.create_customer(data, actor=_actor(request))
            except CustomerMutationError as exc:
                refusal = _mutation_refusal(exc)
                return {**dict(refusal.data), "outcome": "not_applied"}, refusal.status_code
            detail = build_customer_detail(customer.ref)
            return {
                "ok": True,
                "outcome": "applied",
                "customer": projection_data(detail),
                "resource": {"kind": "customer", "ref": customer.ref},
            }, 201

        try:
            result = run_idempotent_mutation(scope=scope, key=key, fingerprint=fingerprint, execute=execute)
            return Response(result.response_body, status=result.response_code)
        except RemoteMutationConflict:
            return Response(
                {"detail": "Esta tentativa já representa outro cliente.", "error": {"code": "intention_conflict"}},
                status=409,
            )
        except RemoteMutationInProgress:
            return Response(
                {"detail": "Cadastro em processamento. Tente novamente em instantes.", "outcome": "unknown"},
                status=202,
            )


@extend_schema_view(
    get=extend_schema(
        tags=["backstage"],
        summary="Customer detail (360 + possible duplicates)",
        responses={200: OpenApiResponse(description="Ficha do cliente."), 404: OpenApiResponse(description="Cadastro inexistente.")},
    ),
    patch=extend_schema(
        tags=["backstage"],
        summary="Edit a customer with optimistic concurrency",
        responses={200: OpenApiResponse(description="Ficha atualizada.")},
    ),
)
class CustomerDetailView(_CustomersBase):
    def get(self, request, ref: str):
        from shopman.backstage.projections.customers import build_customer_detail

        detail = build_customer_detail(ref)
        if detail is None:
            return Response({"detail": "Cliente não encontrado."}, status=404)
        return Response(read_data(customer=projection_data(detail)))

    def patch(self, request, ref: str):
        from shopman.backstage.projections.customers import build_customer_detail

        data = dict(request.data or {})
        key = request.headers.get("Idempotency-Key") or data.pop("idempotencyKey", None)
        if not isinstance(key, str) or not key or len(key) > 128:
            return Response(
                {"detail": "Atualize a ficha e tente novamente.", "error": {"code": "intention_required"}},
                status=400,
            )
        scope = mutation_fingerprint({
            "version": 1,
            "actor": request.user.pk,
            "operation": f"customer-update:{ref}",
        })
        fingerprint = mutation_fingerprint({"scope": scope, "payload": data})

        def execute():
            try:
                customer = customers_service.update_customer(ref, data)
            except CustomerNotFound as exc:
                return {"detail": str(exc), "outcome": "not_applied"}, 404
            except CustomerMutationError as exc:
                refusal = _mutation_refusal(exc)
                return {**dict(refusal.data), "outcome": "not_applied"}, refusal.status_code
            return {
                "ok": True,
                "outcome": "applied",
                "customer": projection_data(build_customer_detail(customer.ref)),
                "resource": {"kind": "customer", "ref": customer.ref},
            }, 200

        try:
            result = run_idempotent_mutation(scope=scope, key=key, fingerprint=fingerprint, execute=execute)
            return Response(result.response_body, status=result.response_code)
        except RemoteMutationConflict:
            return Response(
                {"detail": "Esta tentativa já representa outra edição.", "error": {"code": "intention_conflict"}},
                status=409,
            )
        except RemoteMutationInProgress:
            return Response(
                {"detail": "Edição em processamento. Tente novamente em instantes.", "outcome": "unknown"},
                status=202,
            )


@extend_schema_view(
    post=extend_schema(
        tags=["backstage"],
        summary="Duplicate a customer into a new record",
        responses={201: OpenApiResponse(description="Cópia criada e projetada.")},
    ),
)
class CustomerDuplicateView(_CustomersBase):
    def post(self, request, ref: str):
        from shopman.backstage.projections.customers import build_customer_detail

        data = dict(request.data or {})
        key = request.headers.get("Idempotency-Key") or data.pop("idempotencyKey", None)
        if not isinstance(key, str) or not key or len(key) > 128:
            return Response(
                {"detail": "Atualize a ficha e tente novamente.", "error": {"code": "intention_required"}},
                status=400,
            )
        scope = mutation_fingerprint({
            "version": 1,
            "actor": request.user.pk,
            "operation": f"customer-duplicate:{ref}",
        })
        fingerprint = mutation_fingerprint({"scope": scope, "payload": data})

        def execute():
            try:
                customer = customers_service.duplicate_customer(ref, data, actor=_actor(request))
            except CustomerNotFound as exc:
                return {"detail": str(exc), "outcome": "not_applied"}, 404
            except CustomerMutationError as exc:
                refusal = _mutation_refusal(exc)
                return {**dict(refusal.data), "outcome": "not_applied"}, refusal.status_code
            return {
                "ok": True,
                "outcome": "applied",
                "customer": projection_data(build_customer_detail(customer.ref)),
                "resource": {"kind": "customer", "ref": customer.ref},
            }, 201

        try:
            result = run_idempotent_mutation(scope=scope, key=key, fingerprint=fingerprint, execute=execute)
            return Response(result.response_body, status=result.response_code)
        except RemoteMutationConflict:
            return Response(
                {"detail": "Esta tentativa já representa outra cópia.", "error": {"code": "intention_conflict"}},
                status=409,
            )
        except RemoteMutationInProgress:
            return Response(
                {"detail": "Cópia em processamento. Tente novamente em instantes.", "outcome": "unknown"},
                status=202,
            )


@extend_schema_view(
    post=extend_schema(
        tags=["backstage"],
        summary="Apply one action to several customers at once",
        responses={200: OpenApiResponse(description="Aplicado; diz quantos entraram e quantos ficaram de fora.")},
    ),
)
class CustomerBulkView(_CustomersBase):
    def post(self, request):
        data = dict(request.data or {})
        key = request.headers.get("Idempotency-Key") or data.pop("idempotencyKey", None)
        if not isinstance(key, str) or not key or len(key) > 128:
            return Response(
                {"detail": "Atualize a lista e tente novamente.", "error": {"code": "intention_required"}},
                status=400,
            )
        scope = mutation_fingerprint({
            "version": 1,
            "actor": request.user.pk,
            "operation": "customer-bulk",
        })
        fingerprint = mutation_fingerprint({"scope": scope, "payload": data})

        def execute():
            try:
                result = customers_service.bulk_customers(data, actor=_actor(request))
            except CustomerMutationError as exc:
                refusal = _mutation_refusal(exc)
                return {**dict(refusal.data), "outcome": "not_applied"}, refusal.status_code
            return {"ok": True, "outcome": "applied", **result}, 200

        try:
            result = run_idempotent_mutation(scope=scope, key=key, fingerprint=fingerprint, execute=execute)
            return Response(result.response_body, status=result.response_code)
        except RemoteMutationConflict:
            return Response(
                {"detail": "Esta tentativa já representa outro lote.", "error": {"code": "intention_conflict"}},
                status=409,
            )
        except RemoteMutationInProgress:
            return Response(
                {"detail": "Lote em processamento. Tente novamente em instantes.", "outcome": "unknown"},
                status=202,
            )


@extend_schema_view(
    post=extend_schema(
        tags=["backstage"],
        summary="Create a customer address with an idempotent intention",
        responses={201: OpenApiResponse(description="Endereço criado e ficha atualizada.")},
    ),
)
class CustomerAddressListView(_CustomersBase):
    def post(self, request, ref: str):
        from shopman.backstage.projections.customers import build_customer_detail

        data = dict(request.data or {})
        key = request.headers.get("Idempotency-Key") or data.pop("idempotencyKey", None)
        if not isinstance(key, str) or not key or len(key) > 128:
            return Response(
                {"detail": "Atualize a ficha e tente novamente.", "error": {"code": "intention_required"}},
                status=400,
            )
        scope = mutation_fingerprint({
            "version": 1,
            "actor": request.user.pk,
            "operation": f"customer-address-create:{ref}",
        })
        fingerprint = mutation_fingerprint({"scope": scope, "payload": data})

        def execute():
            try:
                address = customers_service.create_address(ref, data)
            except CustomerNotFound as exc:
                return {"detail": str(exc), "outcome": "not_applied"}, 404
            except CustomerMutationError as exc:
                refusal = _mutation_refusal(exc)
                return {**dict(refusal.data), "outcome": "not_applied"}, refusal.status_code
            return {
                "ok": True,
                "outcome": "applied",
                "customer": projection_data(build_customer_detail(ref)),
                "resource": {"kind": "customer-address", "ref": str(address.pk)},
            }, 201

        try:
            result = run_idempotent_mutation(scope=scope, key=key, fingerprint=fingerprint, execute=execute)
            return Response(result.response_body, status=result.response_code)
        except RemoteMutationConflict:
            return Response(
                {"detail": "Esta tentativa já representa outro endereço.", "error": {"code": "intention_conflict"}},
                status=409,
            )
        except RemoteMutationInProgress:
            return Response(
                {"detail": "Endereço em processamento. Tente novamente em instantes.", "outcome": "unknown"},
                status=202,
            )


@extend_schema_view(
    patch=extend_schema(
        tags=["backstage"],
        summary="Edit a customer address with optimistic concurrency",
        responses={200: OpenApiResponse(description="Endereço e ficha atualizados.")},
    ),
    delete=extend_schema(
        tags=["backstage"],
        summary="Remove a customer address with an idempotent intention",
        responses={200: OpenApiResponse(description="Endereço removido e ficha atualizada.")},
    ),
)
class CustomerAddressDetailView(_CustomersBase):
    def patch(self, request, ref: str, address_id: int):
        from shopman.backstage.projections.customers import build_customer_detail

        data = dict(request.data or {})
        key = request.headers.get("Idempotency-Key") or data.pop("idempotencyKey", None)
        if not isinstance(key, str) or not key or len(key) > 128:
            return Response(
                {"detail": "Atualize a ficha e tente novamente.", "error": {"code": "intention_required"}},
                status=400,
            )
        scope = mutation_fingerprint({
            "version": 1,
            "actor": request.user.pk,
            "operation": f"customer-address-update:{ref}:{address_id}",
        })
        fingerprint = mutation_fingerprint({"scope": scope, "payload": data})

        def execute():
            try:
                customers_service.update_address(ref, address_id, data)
            except CustomerNotFound as exc:
                return {"detail": str(exc), "outcome": "not_applied"}, 404
            except CustomerMutationError as exc:
                refusal = _mutation_refusal(exc)
                return {**dict(refusal.data), "outcome": "not_applied"}, refusal.status_code
            return {
                "ok": True,
                "outcome": "applied",
                "customer": projection_data(build_customer_detail(ref)),
                "resource": {"kind": "customer-address", "ref": str(address_id)},
            }, 200

        try:
            result = run_idempotent_mutation(scope=scope, key=key, fingerprint=fingerprint, execute=execute)
            return Response(result.response_body, status=result.response_code)
        except RemoteMutationConflict:
            return Response(
                {"detail": "Esta tentativa já representa outra edição de endereço.", "error": {"code": "intention_conflict"}},
                status=409,
            )
        except RemoteMutationInProgress:
            return Response(
                {"detail": "Edição do endereço em processamento. Tente novamente em instantes.", "outcome": "unknown"},
                status=202,
            )

    def delete(self, request, ref: str, address_id: int):
        from shopman.backstage.projections.customers import build_customer_detail

        data = dict(request.data or {})
        key = request.headers.get("Idempotency-Key") or data.pop("idempotencyKey", None)
        if not isinstance(key, str) or not key or len(key) > 128:
            return Response(
                {"detail": "Atualize a ficha e tente novamente.", "error": {"code": "intention_required"}},
                status=400,
            )
        scope = mutation_fingerprint({
            "version": 1,
            "actor": request.user.pk,
            "operation": f"customer-address-delete:{ref}:{address_id}",
        })
        fingerprint = mutation_fingerprint({"scope": scope, "payload": data})

        def execute():
            try:
                customers_service.delete_address(ref, address_id, data)
            except CustomerNotFound as exc:
                return {"detail": str(exc), "outcome": "not_applied"}, 404
            except CustomerMutationError as exc:
                refusal = _mutation_refusal(exc)
                return {**dict(refusal.data), "outcome": "not_applied"}, refusal.status_code
            return {
                "ok": True,
                "outcome": "applied",
                "customer": projection_data(build_customer_detail(ref)),
                "resource": {"kind": "customer-address", "ref": str(address_id)},
            }, 200

        try:
            result = run_idempotent_mutation(scope=scope, key=key, fingerprint=fingerprint, execute=execute)
            return Response(result.response_body, status=result.response_code)
        except RemoteMutationConflict:
            return Response(
                {"detail": "Esta tentativa já representa outra remoção.", "error": {"code": "intention_conflict"}},
                status=409,
            )
        except RemoteMutationInProgress:
            return Response(
                {"detail": "Remoção em processamento. Tente novamente em instantes.", "outcome": "unknown"},
                status=202,
            )


@extend_schema_view(
    get=extend_schema(
        tags=["backstage"],
        summary="Read-only preview of a customer merge",
        responses={200: OpenApiResponse(description="O que a unificação faria; nada é gravado.")},
    ),
)
class CustomerMergePreviewView(_CustomersBase):
    def get(self, request):
        from shopman.backstage.projections.customers import build_merge_preview

        try:
            source, target, preview = customers_service.preview_merge(
                source_ref=request.query_params.get("source_ref") or "",
                target_ref=request.query_params.get("target_ref") or "",
            )
        except CustomerMergeError as exc:
            return _refusal(exc)
        return Response(read_data(preview=projection_data(build_merge_preview(source, target, preview))))


@extend_schema_view(
    post=extend_schema(
        tags=["backstage"],
        summary="Merge two customer records (source is absorbed into target)",
        responses={200: OpenApiResponse(description="Unificação feita; traz o id para desfazer.")},
    ),
)
class CustomerMergeView(_CustomersBase):
    def post(self, request):
        body = request.data or {}
        try:
            result = customers_service.merge_customers(
                source_ref=str(body.get("source_ref") or ""),
                target_ref=str(body.get("target_ref") or ""),
                actor=_actor(request),
            )
        except CustomerMergeError as exc:
            return _refusal(exc)
        return Response(
            {
                "ok": True,
                "source_ref": result.source_ref,
                "target_ref": result.target_ref,
                "audit_id": result.audit_id,
            }
        )


@extend_schema_view(
    get=extend_schema(
        tags=["backstage"],
        summary="Customer merge history (with undo window)",
        responses={200: OpenApiResponse(description="Unificações recentes.")},
    ),
)
class CustomerMergeListView(_CustomersBase):
    def get(self, request):
        from shopman.backstage.projections.customers import build_merge_audit_list

        return Response(read_data(merges=projection_data(build_merge_audit_list())))


@extend_schema_view(
    post=extend_schema(
        tags=["backstage"],
        summary="Undo a customer merge inside the undo window",
        responses={200: OpenApiResponse(description="Unificação desfeita.")},
    ),
)
class CustomerMergeUndoView(_CustomersBase):
    def post(self, request, audit_id: str):
        try:
            customers_service.undo_merge(audit_id=audit_id, actor=_actor(request))
        except CustomerMergeError as exc:
            return _refusal(exc)
        return Response({"ok": True})
