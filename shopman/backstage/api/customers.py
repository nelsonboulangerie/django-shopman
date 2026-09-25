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
from shopman.backstage.services.exceptions import CustomerMergeError, CustomerNotFound


def _actor(request) -> str:
    user = getattr(request, "user", None)
    return getattr(user, "username", None) or "gestor"


def _refusal(exc: CustomerMergeError) -> Response:
    status = 404 if isinstance(exc, CustomerNotFound) else 422
    return Response({"detail": str(exc)}, status=status)


class _CustomersBase(OperationalObservationMixin, APIView):
    permission_classes = [HasBackstagePermission]
    required_permission = "shop.manage_customers"


@extend_schema_view(
    get=extend_schema(
        tags=["backstage"],
        summary="Customer list (search + filters, paginated)",
        responses={200: OpenApiResponse(description="Página de clientes ativos.")},
    ),
)
class CustomerListView(_CustomersBase):
    def get(self, request):
        from shopman.backstage.projections.customers import build_customer_list

        listing = build_customer_list(
            query=request.query_params.get("q") or "",
            filter_ref=request.query_params.get("filter") or "all",
            page=as_int(request.query_params.dict(), "page", default=1, min_value=1),
        )
        return Response(read_data(list=projection_data(listing)))


@extend_schema_view(
    get=extend_schema(
        tags=["backstage"],
        summary="Customer detail (360 + possible duplicates)",
        responses={200: OpenApiResponse(description="Ficha do cliente."), 404: OpenApiResponse(description="Cadastro inexistente.")},
    ),
)
class CustomerDetailView(_CustomersBase):
    def get(self, request, ref: str):
        from shopman.backstage.projections.customers import build_customer_detail

        detail = build_customer_detail(ref)
        if detail is None:
            return Response({"detail": "Cliente não encontrado."}, status=404)
        return Response(read_data(customer=projection_data(detail)))


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
