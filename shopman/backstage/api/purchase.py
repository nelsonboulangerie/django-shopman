"""Backstage API for the Compras operator surface."""

from __future__ import annotations

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from shopman.backstage.api.projections import projection_data
from shopman.backstage.projections.purchase import build_purchase
from shopman.backstage.projections.purchase_count import build_purchase_count
from shopman.backstage.services import purchase as purchase_service
from shopman.backstage.services import purchase_catalog as purchase_catalog_service
from shopman.backstage.services import purchase_count as purchase_count_service
from shopman.backstage.services.purchase import PurchaseError
from shopman.shop.observability import ServerTimingMixin
from shopman.shop.services.remote_mutations import (
    RemoteMutationConflict,
    RemoteMutationInProgress,
    mutation_fingerprint,
    run_idempotent_mutation,
)

from .permissions import HasBackstagePermission

# Contagem é auditoria de estoque: além de operar Compras, só quem tem o papel
# de dono/gestor com `audit_stock` enxerga e ajusta o saldo dos insumos.
PURCHASE_COUNT_PERMISSIONS = ("backstage.operate_purchase", "backstage.audit_stock")


def _purchase_body(projection, *, message: str = "", resource: dict | None = None) -> dict:
    body = {"ok": True, "outcome": "applied", "purchase": projection_data(projection)}
    if message:
        body["message"] = message
    if resource:
        body["resource"] = resource
    return body


def _purchase_response(projection, *, message: str = "", resource: dict | None = None) -> Response:
    return Response(_purchase_body(projection, message=message, resource=resource))


def _error_response(exc: PurchaseError) -> Response:
    # Dialeto canônico {detail, field, errors} (docs/reference/errors.md) +
    # `error.code` como superset estável, no molde do PDV. `field` mora no
    # topo — era aninhado em `error`, um terceiro formato que nenhuma
    # superfície esperava.
    payload: dict = {"detail": str(exc), "error": {"code": exc.code}}
    if exc.field:
        payload["field"] = exc.field
        payload["errors"] = {exc.field: [str(exc)]}
    if exc.lines:
        # `errors` é o dialeto da casa e fala por CAMPO; um lote erra por
        # LINHA, e a linha não cabe ali sem torcer o contrato. Vai como
        # superset em `error`, no mesmo molde de `error.code`.
        payload["error"]["lines"] = exc.lines
    return Response(payload, status=exc.status_code)


def _catalog_mutation(request, *, operation: str, payload: dict, execute) -> Response:
    """Executa criação/duplicação uma vez, mesmo quando a resposta se perde.

    Cadastro é usado em Wi-Fi de operação. Um reenvio depois de timeout não pode
    criar um segundo fornecedor, contato ou SKU. O mesmo par escopo/chave aceita
    a repetição idêntica e recusa a chave reaproveitada com outro conteúdo.
    """
    key = request.headers.get("Idempotency-Key") or payload.get("idempotencyKey")
    if not isinstance(key, str) or not key or len(key) > 128:
        return Response(
            {
                "detail": "Atualize o cadastro e tente novamente.",
                "error": {"code": "intention_required"},
            },
            status=400,
        )
    clean_payload = {name: value for name, value in payload.items() if name != "idempotencyKey"}
    scope = mutation_fingerprint(
        {"version": 1, "actor": request.user.pk, "operation": operation},
    )
    fingerprint = mutation_fingerprint({"scope": scope, "payload": clean_payload})

    def run():
        try:
            projection, message, resource = execute(clean_payload)
        except PurchaseError as exc:
            response = _error_response(exc)
            body = dict(response.data)
            body["outcome"] = "not_applied"
            return body, response.status_code
        return _purchase_body(projection, message=message, resource=resource), 200

    try:
        result = run_idempotent_mutation(scope=scope, key=key, fingerprint=fingerprint, execute=run)
        return Response(result.response_body, status=result.response_code)
    except RemoteMutationConflict:
        return Response(
            {"detail": "Esta tentativa já representa outro cadastro.", "error": {"code": "intention_conflict"}},
            status=409,
        )
    except RemoteMutationInProgress:
        return Response(
            {"detail": "Cadastro em processamento. Tente novamente em instantes.", "outcome": "unknown"},
            status=202,
        )


class PurchaseBoardView(ServerTimingMixin, APIView):
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


class PurchaseReceiptVolumesView(APIView):
    permission_classes = [HasBackstagePermission]
    required_permission = "backstage.operate_purchase"

    @extend_schema(
        tags=["backstage"],
        summary="Record the counted volumes of the NF under conference",
        responses={200: OpenApiResponse(description="Volumes recorded and projection refreshed.")},
    )
    def post(self, request):
        try:
            projection = purchase_service.save_receipt_volumes(dict(request.data or {}), user=request.user)
        except PurchaseError as exc:
            return _error_response(exc)
        return _purchase_response(projection)


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


class PurchaseCostBatchView(APIView):
    """Tabela de preços do fornecedor num gesto só — ver `upsert_costs`."""

    permission_classes = [HasBackstagePermission]
    required_permission = "backstage.operate_purchase"

    @extend_schema(
        tags=["backstage"],
        summary="Create/update several supplier material costs at once",
        responses={200: OpenApiResponse(description="Costs saved and projection refreshed.")},
    )
    def post(self, request):
        try:
            result = purchase_service.upsert_costs(dict(request.data or {}), user=request.user)
        except PurchaseError as exc:
            return _error_response(exc)
        saved = result["saved"]
        return _purchase_response(
            result["purchase"],
            message=f"{saved} custo(s) salvo(s)." if saved != 1 else "1 custo salvo.",
        )


class PurchaseMinStockView(APIView):
    """Estoque mínimo declarado — ver `set_min_stock`."""

    permission_classes = [HasBackstagePermission]
    required_permission = "backstage.operate_purchase"

    @extend_schema(
        tags=["backstage"],
        summary="Declare the minimum stock of several materials",
        responses={200: OpenApiResponse(description="Minimums saved and projection refreshed.")},
    )
    def post(self, request):
        try:
            result = purchase_service.set_min_stock(dict(request.data or {}), user=request.user)
        except PurchaseError as exc:
            return _error_response(exc)
        saved = result["saved"]
        return _purchase_response(
            result["purchase"],
            message="1 mínimo salvo." if saved == 1 else f"{saved} mínimos salvos.",
        )


class PurchaseOpeningView(APIView):
    """"Quando aberto, vira": em que insumo a embalagem se abre — ver `set_opening`."""

    permission_classes = [HasBackstagePermission]
    required_permission = "backstage.operate_purchase"

    @extend_schema(
        tags=["backstage"],
        summary="Declare what a package opens into (opened ingredient, content, shelf life)",
        responses={200: OpenApiResponse(description="Opening declared and projection refreshed.")},
    )
    def post(self, request, material_sku: str):
        try:
            projection, message = purchase_service.set_opening(material_sku, dict(request.data or {}), user=request.user)
        except PurchaseError as exc:
            return _error_response(exc)
        return _purchase_response(projection, message=message)


class PurchaseSaleView(APIView):
    """"Permitir revenda": liga/desliga a venda do item do Compras — ver `set_sale`.

    Decidir vender (e o preço) é poder de catálogo; por isso exige as duas
    permissões: operar o Compras E gerir o catálogo.
    """

    permission_classes = [HasBackstagePermission]
    required_permission = ("backstage.operate_purchase", "shop.manage_catalog")

    @extend_schema(
        tags=["backstage"],
        summary="Turn selling on/off for a purchasable item (same SKU)",
        responses={200: OpenApiResponse(description="Sale record toggled and projection refreshed.")},
    )
    def post(self, request, material_sku: str):
        try:
            projection, message = purchase_service.set_sale(material_sku, dict(request.data or {}), user=request.user)
        except PurchaseError as exc:
            return _error_response(exc)
        return _purchase_response(projection, message=message)


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


class PurchaseCountView(APIView):
    permission_classes = [HasBackstagePermission]
    required_permission = PURCHASE_COUNT_PERMISSIONS

    @extend_schema(
        tags=["backstage"],
        summary="Stock count board (raw ledger position per material)",
        responses={200: OpenApiResponse(description="Materials with current ledger quantity for physical counting.")},
    )
    def get(self, request):
        return Response({"count": projection_data(build_purchase_count())})


class PurchaseCountConfirmView(APIView):
    permission_classes = [HasBackstagePermission]
    required_permission = PURCHASE_COUNT_PERMISSIONS

    @extend_schema(
        tags=["backstage"],
        summary="Confirm a physical stock count into Stockman adjustments",
        responses={200: OpenApiResponse(description="Divergences written as ADJUST moves; count refreshed.")},
    )
    def post(self, request):
        try:
            projection, message = purchase_count_service.submit_count(dict(request.data or {}), user=request.user)
        except PurchaseError as exc:
            return _error_response(exc)
        return Response({"ok": True, "count": projection_data(projection), "message": message})


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
            projection = purchase_service.send_purchase_request(material_sku, user=request.user)
        except PurchaseError as exc:
            return _error_response(exc)
        return _purchase_response(projection, message="Pedido enviado ao canal do fornecedor.")


class PurchaseRequestCancelView(APIView):
    permission_classes = [HasBackstagePermission]
    required_permission = "backstage.operate_purchase"

    @extend_schema(
        tags=["backstage"],
        summary="Cancel the open replenishment request so the material can be ordered again",
        responses={200: OpenApiResponse(description="Open request cleared; the supplier is not notified.")},
    )
    def post(self, request, material_sku: str):
        try:
            projection = purchase_service.cancel_purchase_request(material_sku)
        except PurchaseError as exc:
            return _error_response(exc)
        return _purchase_response(projection, message="Pedido cancelado aqui. Avise o fornecedor.")

# ── Cadastro da Base: insumo, fornecedor, contato e conversão ───────────────
# O Compras já operava; cadastrar o insumo e o fornecedor ainda mandava o
# gestor ao Admin. Estes endpoints chamam `services.purchase_catalog`, que
# compõe o Buyman sem tocar no Core, e devolvem a projeção inteira como as
# demais ações do Compras.


class PurchaseMaterialView(APIView):
    """Cria um insumo do zero (Base > Insumos > Novo insumo)."""

    permission_classes = [HasBackstagePermission]
    required_permission = "backstage.operate_purchase"

    @extend_schema(
        tags=["backstage"],
        summary="Create a purchasable material",
        responses={200: OpenApiResponse(description="Material created and projection refreshed.")},
    )
    def post(self, request):
        data = dict(request.data or {})

        def execute(payload):
            projection, sku = purchase_catalog_service.create_material(payload, user=request.user)
            name = str(payload.get("name") or "").strip()
            return projection, f"Insumo {name} criado.", {"kind": "material", "ref": sku}

        return _catalog_mutation(
            request,
            operation="purchase.material-create",
            payload=data,
            execute=execute,
        )


class PurchaseMaterialDetailView(APIView):
    """Edita o cadastro do insumo. O SKU não muda por aqui."""

    permission_classes = [HasBackstagePermission]
    required_permission = "backstage.operate_purchase"

    @extend_schema(
        tags=["backstage"],
        summary="Update a purchasable material",
        responses={200: OpenApiResponse(description="Material saved and projection refreshed.")},
    )
    def post(self, request, material_sku: str):
        try:
            projection = purchase_catalog_service.update_material(
                material_sku, dict(request.data or {}), user=request.user,
            )
        except PurchaseError as exc:
            return _error_response(exc)
        return _purchase_response(projection, message="Insumo salvo.")


class PurchaseMaterialDuplicateView(APIView):
    """Duplica o conteúdo copiável do insumo num SKU novo."""

    permission_classes = [HasBackstagePermission]
    required_permission = "backstage.operate_purchase"

    @extend_schema(
        tags=["backstage"],
        summary="Duplicate a purchasable material into a new SKU",
        responses={200: OpenApiResponse(description="Copy created and projection refreshed.")},
    )
    def post(self, request, material_sku: str):
        data = dict(request.data or {})

        def execute(payload):
            projection, sku = purchase_catalog_service.duplicate_material(material_sku, payload, user=request.user)
            return projection, f"Cópia criada: {sku}.", {"kind": "material", "ref": sku}

        return _catalog_mutation(
            request,
            operation=f"purchase.material-duplicate:{material_sku}",
            payload=data,
            execute=execute,
        )


class PurchaseSupplierView(APIView):
    """Cria um fornecedor (Base > Fornecedores > Novo fornecedor)."""

    permission_classes = [HasBackstagePermission]
    required_permission = "backstage.operate_purchase"

    @extend_schema(
        tags=["backstage"],
        summary="Create a supplier",
        responses={200: OpenApiResponse(description="Supplier created and projection refreshed.")},
    )
    def post(self, request):
        data = dict(request.data or {})

        def execute(payload):
            projection, ref = purchase_catalog_service.create_supplier(payload, user=request.user)
            return projection, "Fornecedor cadastrado.", {"kind": "supplier", "ref": ref}

        return _catalog_mutation(
            request,
            operation="purchase.supplier-create",
            payload=data,
            execute=execute,
        )


class PurchaseSupplierDetailView(APIView):
    """Edita o cadastro do fornecedor. A referência não muda por aqui."""

    permission_classes = [HasBackstagePermission]
    required_permission = "backstage.operate_purchase"

    @extend_schema(
        tags=["backstage"],
        summary="Update a supplier",
        responses={200: OpenApiResponse(description="Supplier saved and projection refreshed.")},
    )
    def post(self, request, ref: str):
        try:
            projection = purchase_catalog_service.update_supplier(ref, dict(request.data or {}), user=request.user)
        except PurchaseError as exc:
            return _error_response(exc)
        return _purchase_response(projection, message="Fornecedor salvo.")


class PurchaseSupplierDuplicateView(APIView):
    """Duplica o fornecedor, com os contatos e os termos comerciais."""

    permission_classes = [HasBackstagePermission]
    required_permission = "backstage.operate_purchase"

    @extend_schema(
        tags=["backstage"],
        summary="Duplicate a supplier into a new reference",
        responses={200: OpenApiResponse(description="Copy created and projection refreshed.")},
    )
    def post(self, request, ref: str):
        data = dict(request.data or {})

        def execute(payload):
            projection, created_ref = purchase_catalog_service.duplicate_supplier(ref, payload, user=request.user)
            return projection, "Cópia do fornecedor criada.", {"kind": "supplier", "ref": created_ref}

        return _catalog_mutation(
            request,
            operation=f"purchase.supplier-duplicate:{ref}",
            payload=data,
            execute=execute,
        )


class PurchaseSupplierContactView(APIView):
    """Adiciona a pessoa que atende no fornecedor."""

    permission_classes = [HasBackstagePermission]
    required_permission = "backstage.operate_purchase"

    @extend_schema(
        tags=["backstage"],
        summary="Create a supplier contact",
        responses={200: OpenApiResponse(description="Contact created and projection refreshed.")},
    )
    def post(self, request, ref: str):
        data = dict(request.data or {})
        return _catalog_mutation(
            request,
            operation=f"purchase.supplier-contact-create:{ref}",
            payload=data,
            execute=lambda payload: (
                purchase_catalog_service.create_supplier_contact(ref, payload, user=request.user),
                "Contato adicionado.",
                None,
            ),
        )


class PurchaseContactView(APIView):
    """Edita a pessoa do fornecedor, inclusive para aposentá-la."""

    permission_classes = [HasBackstagePermission]
    required_permission = "backstage.operate_purchase"

    @extend_schema(
        tags=["backstage"],
        summary="Update a supplier contact",
        responses={200: OpenApiResponse(description="Contact saved and projection refreshed.")},
    )
    def post(self, request, contact_id: int):
        try:
            projection = purchase_catalog_service.update_supplier_contact(
                contact_id, dict(request.data or {}), user=request.user,
            )
        except PurchaseError as exc:
            return _error_response(exc)
        return _purchase_response(projection, message="Contato salvo.")


class PurchaseConversionDetailView(APIView):
    """Edita uma conversão já declarada (fator, rótulo, tipo, dono, situação)."""

    permission_classes = [HasBackstagePermission]
    required_permission = "backstage.operate_purchase"

    @extend_schema(
        tags=["backstage"],
        summary="Update a declared material conversion",
        responses={200: OpenApiResponse(description="Conversion saved and projection refreshed.")},
    )
    def post(self, request, conversion_id: int):
        try:
            projection, message = purchase_catalog_service.update_conversion(
                conversion_id, dict(request.data or {}), user=request.user,
            )
        except PurchaseError as exc:
            return _error_response(exc)
        return _purchase_response(projection, message=message)

