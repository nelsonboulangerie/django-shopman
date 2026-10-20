"""Prévia/aplicação e exportação CSV da Base do Compras."""

from rest_framework.response import Response
from rest_framework.views import APIView

from shopman.backstage.api.permissions import HasBackstagePermission
from shopman.backstage.api.purchase import _error_response
from shopman.backstage.services import purchase_csv
from shopman.backstage.services.purchase import PurchaseError
from shopman.shop.observability import ServerTimingMixin
from shopman.shop.services.remote_mutations import (
    RemoteMutationConflict,
    RemoteMutationInProgress,
    mutation_fingerprint,
    run_idempotent_mutation,
)


class PurchaseCsvView(ServerTimingMixin, APIView):
    permission_classes = [HasBackstagePermission]
    required_permission = "backstage.operate_purchase"
    server_timing_methods = ("GET", "POST")

    def get(self, request, entity):
        try:
            return Response(purchase_csv.export_table(entity))
        except PurchaseError as exc:
            return _error_response(exc)

    def post(self, request, entity):
        if not isinstance(request.data, dict):
            return Response(
                {
                    "detail": "Escolha o arquivo CSV antes de importar.",
                    "field": "csv",
                    "errors": {"csv": ["Arquivo CSV inválido."]},
                },
                status=400,
            )
        data = dict(request.data)
        try:
            if data.get("preview") is True:
                return Response(purchase_csv.preview_import(entity, data, user=request.user))
            key = request.headers.get("Idempotency-Key")
            if not isinstance(key, str) or not key or len(key) > 128:
                raise PurchaseError("Revise a prévia antes de importar.", code="intention_required")
            scope = mutation_fingerprint({"operation": "purchase.csv", "entity": entity, "actor": request.user.pk})

            def execute():
                try:
                    body = purchase_csv.apply_import(entity, data, user=request.user)
                    if not body["ok"]:
                        return {
                            "detail": "Corrija os registros indicados e refaça a prévia.",
                            "outcome": "not_applied",
                            "error": {"code": "csv_rows_invalid", "lines": body["errors"]},
                            "result": body,
                        }, 400
                    return body, 200
                except PurchaseError as exc:
                    response = _error_response(exc)
                    return dict(response.data), response.status_code

            result = run_idempotent_mutation(
                scope=scope, key=key, fingerprint=mutation_fingerprint(data), execute=execute
            )
            return Response(result.response_body, status=result.response_code)
        except PurchaseError as exc:
            return _error_response(exc)
        except RemoteMutationConflict:
            return Response({"detail": "Esta tentativa já representa outro arquivo."}, status=409)
        except RemoteMutationInProgress:
            return Response(
                {"outcome": "unknown", "detail": "A importação está em processamento. Tente de novo."}, status=202
            )
