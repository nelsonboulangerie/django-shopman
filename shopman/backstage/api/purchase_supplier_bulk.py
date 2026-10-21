"""Gesto único para o lote de fornecedores da Base."""

from rest_framework.response import Response
from rest_framework.views import APIView

from shopman.backstage.api.permissions import HasBackstagePermission
from shopman.backstage.api.purchase import _catalog_mutation
from shopman.backstage.services.purchase_supplier_bulk import set_supplier_archive
from shopman.shop.observability import ServerTimingMixin


class PurchaseSupplierBulkView(ServerTimingMixin, APIView):
    permission_classes = [HasBackstagePermission]
    required_permission = "backstage.operate_purchase"
    server_timing_methods = ("POST",)

    def post(self, request):
        if not isinstance(request.data, dict):
            return Response(
                {
                    "detail": "Marque os fornecedores na lista antes de alterar.",
                    "field": "rows",
                    "errors": {"rows": ["Seleção de fornecedores inválida."]},
                },
                status=400,
            )
        return _catalog_mutation(
            request,
            operation="purchase.supplier-bulk",
            payload=dict(request.data or {}),
            execute=lambda data: set_supplier_archive(data, user=request.user),
        )
