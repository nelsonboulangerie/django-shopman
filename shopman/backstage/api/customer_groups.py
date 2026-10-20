"""CRUD dos grupos comerciais do cliente na superfície Gestor."""

from __future__ import annotations

from drf_spectacular.utils import OpenApiResponse, extend_schema, extend_schema_view
from rest_framework.response import Response
from rest_framework.views import APIView

from shopman.backstage.api.permissions import HasBackstagePermission
from shopman.backstage.api.projections import projection_data, read_data
from shopman.backstage.api.telemetry import OperationalObservationMixin
from shopman.backstage.services import customer_groups as group_service
from shopman.backstage.services.exceptions import CustomerGroupMutationError
from shopman.shop.observability import ServerTimingMixin
from shopman.shop.services.remote_mutations import (
    RemoteMutationConflict,
    RemoteMutationInProgress,
    mutation_fingerprint,
    run_idempotent_mutation,
)


class _CustomerGroupsBase(OperationalObservationMixin, APIView):
    permission_classes = [HasBackstagePermission]
    required_permission = "shop.manage_customers"

    def _idempotent(self, request, *, operation: str, data: dict, execute):
        key = request.headers.get("Idempotency-Key") or data.pop("idempotencyKey", None)
        if not isinstance(key, str) or not key or len(key) > 128:
            return Response(
                {"detail": "Atualize os grupos e tente novamente.", "error": {"code": "intention_required"}},
                status=400,
            )
        scope = mutation_fingerprint({"version": 1, "actor": request.user.pk, "operation": operation})
        fingerprint = mutation_fingerprint({"scope": scope, "payload": data})
        try:
            result = run_idempotent_mutation(scope=scope, key=key, fingerprint=fingerprint, execute=execute)
            return Response(result.response_body, status=result.response_code)
        except RemoteMutationConflict:
            return Response(
                {"detail": "Esta tentativa já representa outra alteração.", "error": {"code": "intention_conflict"}},
                status=409,
            )
        except RemoteMutationInProgress:
            return Response(
                {"detail": "Alteração em processamento. Tente novamente em instantes.", "outcome": "unknown"},
                status=202,
            )


def _refusal(exc: CustomerGroupMutationError) -> tuple[dict, int]:
    status = 404 if exc.code == "not_found" else 409 if exc.code in {"group_changed", "ref_conflict"} else 400
    payload = {"detail": exc.detail, "error": {"code": exc.code}, "outcome": "not_applied"}
    if exc.field:
        payload["field"] = exc.field
        payload["errors"] = {exc.field: [exc.detail]}
    return payload, status


@extend_schema_view(
    get=extend_schema(tags=["backstage"], summary="Customer commercial groups", responses={200: OpenApiResponse(description="Grupos e opções do formulário.")}),
    post=extend_schema(tags=["backstage"], summary="Create customer commercial group", responses={201: OpenApiResponse(description="Grupo criado.")}),
)
class CustomerGroupListView(_CustomerGroupsBase):
    def get(self, request):
        from shopman.backstage.projections.customer_groups import build_customer_group_list

        return Response(read_data(groups=projection_data(build_customer_group_list())))

    def post(self, request):
        from shopman.backstage.projections.customer_groups import build_customer_group_detail

        data = dict(request.data or {})

        def execute():
            try:
                tier = group_service.create_group(data)
            except CustomerGroupMutationError as exc:
                return _refusal(exc)
            return {
                "ok": True,
                "outcome": "applied",
                "group": projection_data(build_customer_group_detail(tier.ref)),
                "resource": {"kind": "customer-group", "ref": tier.ref},
            }, 201

        return self._idempotent(request, operation="customer-group-create", data=data, execute=execute)


@extend_schema_view(
    get=extend_schema(tags=["backstage"], summary="Customer commercial group detail", responses={200: OpenApiResponse(description="Grupo comercial.")}),
    patch=extend_schema(tags=["backstage"], summary="Edit customer commercial group", responses={200: OpenApiResponse(description="Grupo atualizado.")}),
)
class CustomerGroupDetailView(_CustomerGroupsBase):
    def get(self, request, ref: str):
        from shopman.backstage.projections.customer_groups import build_customer_group_detail

        group = build_customer_group_detail(ref)
        if group is None:
            return Response({"detail": "Grupo não encontrado."}, status=404)
        return Response(read_data(group=projection_data(group)))

    def patch(self, request, ref: str):
        from shopman.backstage.projections.customer_groups import build_customer_group_detail

        data = dict(request.data or {})

        def execute():
            try:
                tier = group_service.update_group(ref, data)
            except CustomerGroupMutationError as exc:
                return _refusal(exc)
            return {
                "ok": True,
                "outcome": "applied",
                "group": projection_data(build_customer_group_detail(tier.ref)),
                "resource": {"kind": "customer-group", "ref": tier.ref},
            }, 200

        return self._idempotent(request, operation=f"customer-group-update:{ref}", data=data, execute=execute)


@extend_schema_view(
    post=extend_schema(
        tags=["backstage"],
        summary="Add or remove several customers from one commercial group",
        responses={200: OpenApiResponse(description="Aplicado; diz quem mudou, quem já estava e quem ficou de fora.")},
    ),
)
class CustomerGroupMembersView(ServerTimingMixin, _CustomerGroupsBase):
    """Pôr ou tirar vários clientes de um grupo numa ida (lista de clientes e tela do grupo)."""

    server_timing_methods = ("POST",)

    def post(self, request, ref: str):
        data = dict(request.data or {})
        actor = getattr(request.user, "username", "") or "gestor"

        def execute():
            try:
                result = group_service.change_group_members(ref, data, actor=actor)
            except CustomerGroupMutationError as exc:
                return _refusal(exc)
            return {"ok": True, "outcome": "applied", **result}, 200

        return self._idempotent(request, operation=f"customer-group-members:{ref}", data=data, execute=execute)
