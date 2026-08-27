"""Backstage API for the Compras operator surface."""

from __future__ import annotations

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from shopman.backstage.api.projections import projection_data
from shopman.backstage.projections.purchase import build_purchase
from shopman.backstage.services import purchase as purchase_service
from shopman.backstage.services.purchase import PurchaseError

from .permissions import HasBackstagePermission


def _purchase_response(projection, *, message: str = "") -> Response:
    body = {"ok": True, "purchase": projection_data(projection)}
    if message:
        body["message"] = message
    return Response(body)


def _error_response(exc: PurchaseError) -> Response:
    # Dialeto canônico {detail, field, errors} (docs/reference/errors.md) +
    # `error.code` como superset estável, no molde do PDV. `field` mora no
    # topo — era aninhado em `error`, um terceiro formato que nenhuma
    # superfície esperava.
    payload: dict = {"detail": str(exc), "error": {"code": exc.code}}
    if exc.field:
        payload["field"] = exc.field
        payload["errors"] = {exc.field: [str(exc)]}
    return Response(payload, status=exc.status_code)


class PurchaseBoardView(APIView):
    permission_classes = [HasBackstagePermission]
    required_permission = "backstage.operate_purchase"

    @extend_schema(
        tags=["backstage"],
        summary="Compras projection",
        responses={200: OpenApiResponse(description="Materials, suppliers, costs and active receipt draft.")},
    )
    def get(self, request):
        return Response({"purchase": projection_data(build_purchase())})


class PurchaseScanInvoiceView(APIView):
    permission_classes = [HasBackstagePermission]
    required_permission = "backstage.operate_purchase"

    @extend_schema(
        tags=["backstage"],
        summary="Read an NF QR/access key into a receipt draft",
        responses={200: OpenApiResponse(description="Receipt draft projection.")},
    )
    def post(self, request):
        try:
            projection, message = purchase_service.scan_invoice(str(request.data.get("qrPayload") or ""))
        except PurchaseError as exc:
            return _error_response(exc)
        return _purchase_response(projection, message=message)


class PurchaseConfirmReceiptView(APIView):
    permission_classes = [HasBackstagePermission]
    required_permission = "backstage.operate_purchase"

    @extend_schema(
        tags=["backstage"],
        summary="Confirm material receipt into Stockman",
        responses={200: OpenApiResponse(description="Receipt confirmed and projection refreshed.")},
    )
    def post(self, request):
        try:
            projection = purchase_service.confirm_receipt(dict(request.data or {}), user=request.user)
        except PurchaseError as exc:
            return _error_response(exc)
        return _purchase_response(projection, message="Entrada confirmada no estoque.")


class PurchaseRejectReceiptView(APIView):
    permission_classes = [HasBackstagePermission]
    required_permission = "backstage.operate_purchase"

    @extend_schema(
        tags=["backstage"],
        summary="Record supplier delivery refusal/return",
        responses={200: OpenApiResponse(description="Return/refusal recorded and projection refreshed.")},
    )
    def post(self, request):
        try:
            projection, message = purchase_service.reject_receipt(dict(request.data or {}), user=request.user)
        except PurchaseError as exc:
            return _error_response(exc)
        return _purchase_response(projection, message=message)


class PurchaseCostView(APIView):
    permission_classes = [HasBackstagePermission]
    required_permission = "backstage.operate_purchase"

    @extend_schema(
        tags=["backstage"],
        summary="Create/update a supplier material cost",
        responses={200: OpenApiResponse(description="Cost saved and projection refreshed.")},
    )
    def post(self, request):
        try:
            projection = purchase_service.upsert_cost(dict(request.data or {}), user=request.user)
        except PurchaseError as exc:
            return _error_response(exc)
        return _purchase_response(projection, message="Custo salvo.")


class PurchaseConversionView(APIView):
    """Declarar uma conversão de unidade sem sair do recebimento.

    **Por que é permissão de operador de compras, e não do gestor.** A tentação
    é tratar isto como cadastro mestre — e é, em parte: o fator multiplica
    estoque e dinheiro de toda compra seguinte. Mas o gesto aqui não INVENTA
    número: ele transcreve o que a nota declarou (``conversionSuggestion`` vem
    do par tributável da própria NF-e) com a nota na mão, no momento em que a
    embalagem nova aparece. Exigir o gestor devolveria exatamente o impasse que
    esta rota existe para desfazer — a entrada parada esperando alguém que não
    está no balcão às cinco da manhã.

    É o oposto do gesto da contagem de insumos, que sobrepõe o livro sem
    documento nenhum por trás e por isso é restrito. A conversão fica auditável
    pelo outro lado: a linha guarda ``created_by``, e o Admin continua sendo
    onde ela é corrigida.
    """

    permission_classes = [HasBackstagePermission]
    required_permission = "backstage.operate_purchase"

    @extend_schema(
        tags=["backstage"],
        summary="Declare a material unit conversion from the receipt flow",
        responses={200: OpenApiResponse(description="Conversion declared and projection refreshed.")},
    )
    def post(self, request):
        try:
            projection, message, conversion_id = purchase_service.declare_conversion(
                dict(request.data or {}), user=request.user,
            )
        except PurchaseError as exc:
            return _error_response(exc)
        response = _purchase_response(projection, message=message)
        response.data["conversionId"] = conversion_id
        return response


class PurchaseRequestApproveView(APIView):
    permission_classes = [HasBackstagePermission]
    required_permission = "backstage.operate_purchase"

    @extend_schema(
        tags=["backstage"],
        summary="Approve a replenishment request",
        responses={200: OpenApiResponse(description="Request marked as approved.")},
    )
    def post(self, request, material_sku: str):
        try:
            projection = purchase_service.set_purchase_request_status(material_sku, "approved", user=request.user)
        except PurchaseError as exc:
            return _error_response(exc)
        return _purchase_response(projection, message="Solicitação aprovada.")


class PurchaseRequestSendView(APIView):
    permission_classes = [HasBackstagePermission]
    required_permission = "backstage.operate_purchase"

    @extend_schema(
        tags=["backstage"],
        summary="Mark a replenishment request as sent",
        responses={200: OpenApiResponse(description="Request marked as sent.")},
    )
    def post(self, request, material_sku: str):
        try:
            projection = purchase_service.set_purchase_request_status(material_sku, "sent", user=request.user)
        except PurchaseError as exc:
            return _error_response(exc)
        return _purchase_response(projection, message="Pedido enviado ao canal do fornecedor.")
