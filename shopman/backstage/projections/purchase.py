"""PurchaseProjection — read model for the Compras operator app.

Composes Buyman's upstream master data, Stockman's ledger, and Craftsman's
recipes into the contract consumed by ``surfaces/purchase-nuxt``. The domain
packages stay agnostic: this file is a Backstage projection, not Core behavior.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta
from decimal import ROUND_CEILING, Decimal, InvalidOperation
from statistics import median
from typing import Any

from django.apps import apps
from django.db.models import Sum
from django.utils import timezone

from shopman.shop.purchase_policy import PurchasePolicy, resolve_purchase_policy

logger = logging.getLogger(__name__)

REQUEST_STATUSES = {"review", "approved", "sent"}


@dataclass(frozen=True)
class MaterialProjection:
    sku: str
    name: str
    unit: str
    shelfLifeDays: int | None
    isActive: bool
    category: str
    stockOnHand: float
    dailyUse: float
    minStock: float
    recipes: tuple[str, ...]
    leadTimeDays: float
    replenishAtDays: float
    suggestedQty: float
    stockIsApproximate: bool


@dataclass(frozen=True)
class SupplierProjection:
    ref: str
    name: str
    document: str
    contact: str
    leadTimeDays: int
    reliabilityPercent: int
    isActive: bool
    lastDeliveryAt: str
    paymentTerm: str


@dataclass(frozen=True)
class MaterialConversionProjection:
    id: str
    materialSku: str
    supplierRef: str | None
    label: str
    toBaseFactor: float
    kind: str
    isActive: bool


@dataclass(frozen=True)
class SupplierMaterialCostProjection:
    id: str
    materialSku: str
    supplierRef: str
    conversionId: str | None
    costQ: int
    isPreferred: bool
    updatedAt: str


@dataclass(frozen=True)
class ReceiptConversionSuggestionProjection:
    """O fator que a NF permite propor, e de onde ele saiu.

    ``factor`` viaja como **texto** de propósito: ele volta para o servidor no
    gesto de declarar a conversão, e ``MaterialConversion.to_base_factor`` tem
    seis casas. Passar por ``float`` aqui seria perder precisão de um número que
    multiplica estoque e dinheiro.
    """

    label: str
    factor: str
    kind: str
    source: str
    note: str


@dataclass(frozen=True)
class ReceiptLineProjection:
    id: str
    materialSku: str
    suggestedMaterialSku: str
    suggestionScore: int
    conversionId: str | None
    requiresConversion: bool
    conversionSuggestion: ReceiptConversionSuggestionProjection | None
    purchaseQty: float
    costInput: str
    expiryDate: str
    lineNote: str
    invoiceDescription: str
    invoiceQty: float
    invoiceUnit: str
    invoiceTaxQty: float
    invoiceTaxUnit: str
    invoiceTotal: str
    invoiceProductCode: str
    invoiceEan: str
    checked: bool


@dataclass(frozen=True)
class ActiveReceiptProjection:
    mode: str
    supplierRef: str
    invoiceInput: str
    note: str
    lines: tuple[ReceiptLineProjection, ...]


@dataclass(frozen=True)
class PurchaseProjection:
    materials: tuple[MaterialProjection, ...]
    suppliers: tuple[SupplierProjection, ...]
    conversions: tuple[MaterialConversionProjection, ...]
    costs: tuple[SupplierMaterialCostProjection, ...]
    purchaseRequestStatuses: dict[str, str]
    activeReceipt: ActiveReceiptProjection


def build_purchase(*, active_receipt: dict[str, Any] | None = None) -> PurchaseProjection:
    """Build the full purchase operator projection."""
    Material = apps.get_model("buyman", "Material")
    Supplier = apps.get_model("buyman", "Supplier")
    MaterialConversion = apps.get_model("buyman", "MaterialConversion")
    SupplierMaterialCost = apps.get_model("buyman", "SupplierMaterialCost")

    material_rows = list(Material.objects.all().order_by("-is_active", "sku"))
    supplier_rows = list(Supplier.objects.all().order_by("-is_active", "name", "ref"))
    skus = [material.sku for material in material_rows]
    supplier_refs = [supplier.ref for supplier in supplier_rows]

    policy = _purchase_policy()
    stock_on_hand = _stock_on_hand_map(skus)
    daily_use = _daily_use_map(skus, days=policy["consumption_window_days"])
    recipes = _recipes_map(skus)
    last_delivery = _last_delivery_map(supplier_refs)
    lead_times = _lead_time_map(skus, policy=policy)
    approximate_stock = _approximate_stock_skus(material_rows, policy=policy)

    suppliers = tuple(_supplier_projection(supplier, last_delivery.get(supplier.ref, "")) for supplier in supplier_rows)
    materials = tuple(
        _material_projection(
            material,
            stock_on_hand=stock_on_hand.get(material.sku, Decimal("0")),
            daily_use=daily_use.get(material.sku, Decimal("0")),
            recipes=recipes.get(material.sku, ()),
            lead_time_days=lead_times.get(material.sku, Decimal(policy["min_lead_time_days"])),
            stock_is_approximate=material.sku in approximate_stock,
            policy=policy,
        )
        for material in material_rows
    )
    conversions = tuple(
        MaterialConversionProjection(
            id=str(row.pk),
            materialSku=row.material.sku,
            supplierRef=row.supplier.ref if row.supplier_id else None,
            label=row.label,
            toBaseFactor=_number(row.to_base_factor),
            kind=row.kind,
            isActive=bool(row.is_active),
        )
        for row in MaterialConversion.objects.select_related("material", "supplier").order_by(
            "material__sku", "supplier__ref", "label",
        )
    )
    costs = tuple(
        SupplierMaterialCostProjection(
            id=str(row.pk),
            materialSku=row.material.sku,
            supplierRef=row.supplier.ref,
            conversionId=str(row.conversion_id) if row.conversion_id else None,
            costQ=int(row.cost_q),
            isPreferred=bool(row.is_preferred),
            updatedAt=row.updated_at.date().isoformat() if row.updated_at else "",
        )
        for row in SupplierMaterialCost.objects.select_related("material", "supplier", "conversion").order_by(
            "material__sku", "supplier__name",
        )
    )
    statuses = {
        material.sku: status
        for material in material_rows
        if (status := _purchase_request_status(material)) in REQUEST_STATUSES
    }

    default_supplier_ref = supplier_rows[0].ref if supplier_rows else ""
    return PurchaseProjection(
        materials=materials,
        suppliers=suppliers,
        conversions=conversions,
        costs=costs,
        purchaseRequestStatuses=statuses,
        activeReceipt=_active_receipt(active_receipt, default_supplier_ref=default_supplier_ref),
    )


def _material_projection(
    material,
    *,
    stock_on_hand: Decimal,
    daily_use: Decimal,
    recipes: tuple[str, ...],
    lead_time_days: Decimal,
    stock_is_approximate: bool,
    policy: dict[str, int],
) -> MaterialProjection:
    meta = _purchase_meta(material)
    replenish_at = lead_time_days + Decimal(policy["review_period_days"]) + Decimal(policy["safety_days"])
    min_stock = _meta_decimal(meta, "min_stock", "minStock", default=None)
    if min_stock is None:
        min_stock = daily_use * replenish_at if daily_use > 0 else Decimal("0")
    suggested = _suggested_qty(
        stock_on_hand=stock_on_hand,
        daily_use=daily_use,
        min_stock=min_stock,
        replenish_at=replenish_at,
        shelf_life_days=material.shelf_life_days,
    )
    category = _meta_str(meta, "category") or "Insumos"
    return MaterialProjection(
        sku=material.sku,
        name=material.name,
        unit=material.unit,
        shelfLifeDays=material.shelf_life_days,
        isActive=bool(material.is_active),
        category=category,
        stockOnHand=_number(stock_on_hand),
        dailyUse=_number(daily_use),
        minStock=_number(min_stock),
        recipes=recipes,
        leadTimeDays=_number(lead_time_days),
        replenishAtDays=_number(replenish_at),
        suggestedQty=_number(suggested),
        stockIsApproximate=stock_is_approximate,
    )


def _approximate_stock_skus(material_rows: list[Any], *, policy: dict[str, int]) -> set[str]:
    """Insumos cujo saldo atravessou uma ponte aproximada e ainda carrega o ``≈``.

    O carimbo está no `Move` (``metadata.converted_via.approximate``, gravado no
    recebimento); aqui ele vira a pergunta que a tela faz: *dá para confiar neste
    número como medido?* A R3 da ADR-024 diz que a incerteza acompanha o número
    até a tela — some o ``≈``, some a informação.

    **A janela erra de propósito para o lado seguro.** Saber quando a entrada
    aproximada de fato saiu do estoque exigiria rastrear lote a lote; em vez
    disso vale a validade do insumo (depois dela aquele lote não está mais lá) e,
    quando não há validade, a janela de consumo da política. O resultado é que o
    ``≈`` às vezes fica um pouco mais do que precisava — e isso é o erro certo a
    cometer: marcar de menos esconderia a incerteza, que é o oposto do que a
    regra existe para fazer.
    """
    skus = [material.sku for material in material_rows]
    if not skus:
        return set()
    try:
        Move = apps.get_model("stockman", "Move")
        window = {
            material.sku: material.shelf_life_days or policy["consumption_window_days"]
            for material in material_rows
        }
        oldest = timezone.now() - timedelta(days=max(window.values()))
        rows = Move.objects.filter(
            quant__sku__in=skus,
            delta__gt=0,
            timestamp__gte=oldest,
            metadata__converted_via__approximate=True,
        ).values_list("quant__sku", "timestamp")
        now = timezone.now()
        return {
            sku
            for sku, timestamp in rows
            if (now - timestamp).days <= window.get(sku, policy["consumption_window_days"])
        }
    except Exception:
        logger.debug("purchase.approximate_stock_failed", exc_info=True)
        return set()


def _suggested_qty(
    *,
    stock_on_hand: Decimal,
    daily_use: Decimal,
    min_stock: Decimal,
    replenish_at: Decimal,
    shelf_life_days: int | None,
) -> Decimal:
    """Quantidade a repor: cobre o ciclo prazo+revisão+segurança, sem passar da validade."""
    target = max(min_stock, daily_use * replenish_at)
    need = target - stock_on_hand
    if need <= 0:
        return Decimal("0")
    if shelf_life_days and daily_use > 0:
        consumable = daily_use * Decimal(shelf_life_days) - stock_on_hand
        if consumable <= 0:
            return Decimal("0")
        need = min(need, consumable)
    return need.to_integral_value(rounding=ROUND_CEILING)


def _supplier_projection(supplier, last_delivery_at: str) -> SupplierProjection:
    meta = _purchase_meta(supplier)
    contact = _meta_str(meta, "contact") or supplier.email or supplier.phone
    return SupplierProjection(
        ref=supplier.ref,
        name=supplier.name,
        document=supplier.document,
        contact=contact,
        leadTimeDays=_meta_int(meta, "lead_time_days", "leadTimeDays", default=0),
        reliabilityPercent=_meta_int(meta, "reliability_percent", "reliabilityPercent", default=100),
        isActive=bool(supplier.is_active),
        lastDeliveryAt=_meta_str(meta, "last_delivery_at", "lastDeliveryAt") or last_delivery_at,
        paymentTerm=_meta_str(meta, "payment_term", "paymentTerm") or "A combinar",
    )


def _active_receipt(active_receipt: dict[str, Any] | None, *, default_supplier_ref: str) -> ActiveReceiptProjection:
    data = dict(active_receipt or {})
    if active_receipt is None:
        supplier_ref = default_supplier_ref
    elif "supplierRef" in data or "supplier_ref" in data:
        supplier_ref = str(data.get("supplierRef", data.get("supplier_ref", "")) or "")
    else:
        supplier_ref = default_supplier_ref
    return ActiveReceiptProjection(
        mode=str(data.get("mode") or "invoice"),
        supplierRef=supplier_ref,
        invoiceInput=str(data.get("invoiceInput") or data.get("invoice_input") or ""),
        note=str(data.get("note") or ""),
        lines=tuple(_receipt_line_projection(line) for line in data.get("lines") or ()),
    )


def _receipt_line_projection(line: dict[str, Any]) -> ReceiptLineProjection:
    return ReceiptLineProjection(
        id=str(line.get("id") or ""),
        materialSku=str(line.get("materialSku") or line.get("material_sku") or ""),
        suggestedMaterialSku=str(line.get("suggestedMaterialSku") or line.get("suggested_material_sku") or ""),
        suggestionScore=int(_decimal(line.get("suggestionScore", line.get("suggestion_score", 0)) or 0)),
        conversionId=(
            str(line.get("conversionId") or line.get("conversion_id"))
            if line.get("conversionId") or line.get("conversion_id")
            else None
        ),
        requiresConversion=bool(line.get("requiresConversion") or line.get("requires_conversion")),
        conversionSuggestion=_conversion_suggestion_projection(
            line.get("conversionSuggestion") or line.get("conversion_suggestion"),
        ),
        purchaseQty=_number(_decimal(line.get("purchaseQty", line.get("purchase_qty", 0)))),
        costInput=str(line.get("costInput") or line.get("cost_input") or ""),
        expiryDate=str(line.get("expiryDate") or line.get("expiry_date") or ""),
        lineNote=str(line.get("lineNote") or line.get("line_note") or line.get("note") or ""),
        invoiceDescription=str(line.get("invoiceDescription") or line.get("invoice_description") or ""),
        invoiceQty=_number(_decimal(line.get("invoiceQty", line.get("invoice_qty", 0)))),
        invoiceUnit=str(line.get("invoiceUnit") or line.get("invoice_unit") or ""),
        invoiceTaxQty=_number(_decimal(line.get("invoiceTaxQty", line.get("invoice_tax_qty", 0)))),
        invoiceTaxUnit=str(line.get("invoiceTaxUnit") or line.get("invoice_tax_unit") or ""),
        invoiceTotal=str(line.get("invoiceTotal") or line.get("invoice_total") or ""),
        invoiceProductCode=str(line.get("invoiceProductCode") or line.get("invoice_product_code") or ""),
        invoiceEan=str(line.get("invoiceEan") or line.get("invoice_ean") or ""),
        checked=bool(line.get("checked")),
    )


def _conversion_suggestion_projection(raw: Any) -> ReceiptConversionSuggestionProjection | None:
    if not isinstance(raw, dict):
        return None
    factor = _decimal(raw.get("factor"))
    label = str(raw.get("label") or "").strip()
    if not label or factor <= 0:
        return None
    return ReceiptConversionSuggestionProjection(
        label=label,
        factor=str(factor),
        kind=str(raw.get("kind") or "conventional"),
        source=str(raw.get("source") or ""),
        note=str(raw.get("note") or ""),
    )


def _stock_on_hand_map(skus: list[str]) -> dict[str, Decimal]:
    if not skus:
        return {}
    try:
        from shopman.stockman import stock

        result: dict[str, Decimal] = {}
        for sku in skus:
            try:
                result[sku] = Decimal(stock.available(sku))
            except Exception:
                logger.debug("purchase.stock_available_failed sku=%s", sku, exc_info=True)
                result[sku] = Decimal("0")
        return result
    except Exception:
        logger.debug("purchase.stock_service_unavailable", exc_info=True)
        return {sku: Decimal("0") for sku in skus}


def _purchase_policy() -> dict[str, int]:
    """Política de reposição: Shop.defaults['purchase'] (Admin) sobre os defaults
    tipados (``PurchasePolicy``, shopman/shop/purchase_policy.py)."""
    try:
        return resolve_purchase_policy().to_dict()
    except Exception:
        logger.debug("purchase.policy_load_failed", exc_info=True)
        return PurchasePolicy().to_dict()


def _lead_time_map(skus: list[str], *, policy: dict[str, int]) -> dict[str, Decimal]:
    """Prazo de entrega por insumo: mediana do histórico real (pedido enviado →
    primeira entrada `buy`); sem histórico, o prazo cadastrado no fornecedor
    preferencial; sem ambos, o mínimo da política."""
    floor = Decimal(policy["min_lead_time_days"])
    result = dict.fromkeys(skus, floor)
    if not skus:
        return result
    try:
        SupplierMaterialCost = apps.get_model("buyman", "SupplierMaterialCost")
        for cost in SupplierMaterialCost.objects.filter(
            material__sku__in=skus, is_preferred=True,
        ).select_related("material", "supplier"):
            declared = _meta_decimal(_purchase_meta(cost.supplier), "lead_time_days", "leadTimeDays", default=None)
            if declared and declared > 0:
                result[cost.material.sku] = max(declared, floor)
    except Exception:
        logger.debug("purchase.lead_time_declared_failed", exc_info=True)
    try:
        from shopman.shop.directives import NOTIFICATION_SEND

        Directive = apps.get_model("orderman", "Directive")
        Move = apps.get_model("stockman", "Move")
        since = timezone.now() - timedelta(days=policy["lead_time_history_days"])
        requests: dict[str, list[Any]] = {}
        rows = Directive.objects.filter(
            topic=NOTIFICATION_SEND, created_at__gte=since, payload__event="purchase_request",
        ).values_list("payload", "created_at")
        for payload, created_at in rows:
            sku = str(((payload or {}).get("context") or {}).get("material_sku") or "")
            if sku in result:
                requests.setdefault(sku, []).append(created_at)
        if requests:
            buys: dict[str, list[Any]] = {}
            buy_rows = Move.objects.filter(
                quant__sku__in=list(requests), delta__gt=0, kind="buy", timestamp__gte=since,
            ).values_list("quant__sku", "timestamp")
            for sku, timestamp in buy_rows:
                buys.setdefault(sku, []).append(timestamp)
            cap = policy["lead_time_max_days"]
            for sku, sent_times in requests.items():
                samples: list[float] = []
                deliveries = sorted(buys.get(sku, ()))
                for sent in sorted(sent_times):
                    arrival = next((ts for ts in deliveries if ts >= sent), None)
                    if arrival is None:
                        continue
                    days = (arrival - sent).total_seconds() / 86400
                    if 0 < days <= cap:
                        samples.append(days)
                if samples:
                    result[sku] = max(Decimal(str(round(median(samples), 1))), floor)
    except Exception:
        logger.debug("purchase.lead_time_history_failed", exc_info=True)
    return result


def _daily_use_map(skus: list[str], *, days: int = 14) -> dict[str, Decimal]:
    if not skus:
        return {}
    try:
        Move = apps.get_model("stockman", "Move")
        since = timezone.now() - timedelta(days=days)
        rows = (
            Move.objects.filter(quant__sku__in=skus, delta__lt=0, timestamp__gte=since)
            .values("quant__sku")
            .annotate(total=Sum("delta"))
        )
        divisor = Decimal(days)
        return {
            row["quant__sku"]: abs(Decimal(row["total"] or 0)) / divisor
            for row in rows
        }
    except Exception:
        logger.debug("purchase.daily_use_failed", exc_info=True)
        return {}


def _recipes_map(skus: list[str]) -> dict[str, tuple[str, ...]]:
    if not skus:
        return {}
    try:
        RecipeItem = apps.get_model("craftsman", "RecipeItem")
        rows = (
            RecipeItem.objects.filter(input_sku__in=skus, recipe__is_active=True)
            .select_related("recipe")
            .order_by("input_sku", "recipe__name", "recipe__ref")
        )
        result: dict[str, list[str]] = {}
        seen: dict[str, set[str]] = {}
        for row in rows:
            label = row.recipe.name or row.recipe.ref
            bucket = result.setdefault(row.input_sku, [])
            if label not in seen.setdefault(row.input_sku, set()):
                bucket.append(label)
                seen[row.input_sku].add(label)
        return {sku: tuple(names) for sku, names in result.items()}
    except Exception:
        logger.debug("purchase.recipes_failed", exc_info=True)
        return {}


def _last_delivery_map(supplier_refs: list[str]) -> dict[str, str]:
    if not supplier_refs:
        return {}
    try:
        Move = apps.get_model("stockman", "Move")
        result: dict[str, str] = {}
        for move in (
            Move.objects.filter(delta__gt=0, kind="buy")
            .only("timestamp", "metadata")
            .order_by("-timestamp")[:500]
        ):
            ref = str((move.metadata or {}).get("purchase_supplier_ref") or "")
            if ref in supplier_refs and ref not in result:
                result[ref] = timezone.localtime(move.timestamp).date().isoformat()
            if len(result) == len(supplier_refs):
                break
        return result
    except Exception:
        logger.debug("purchase.last_delivery_failed", exc_info=True)
        return {}


def _purchase_request_status(material) -> str:
    meta = _purchase_meta(material)
    return _meta_str(meta, "request_status", "requestStatus")


def _purchase_meta(obj) -> dict[str, Any]:
    metadata = dict(getattr(obj, "metadata", None) or {})
    nested = metadata.get("purchase")
    if isinstance(nested, dict):
        return {**metadata, **nested}
    return metadata


def _meta_str(meta: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = meta.get(key)
        if value not in (None, ""):
            return str(value).strip()
    return ""


def _meta_int(meta: dict[str, Any], *keys: str, default: int = 0) -> int:
    raw = _meta_str(meta, *keys)
    if not raw:
        return default
    try:
        return int(Decimal(raw.replace(",", ".")))
    except (InvalidOperation, ValueError):
        return default


def _meta_decimal(meta: dict[str, Any], *keys: str, default: Decimal | None = Decimal("0")) -> Decimal | None:
    for key in keys:
        if key in meta and meta.get(key) not in (None, ""):
            return _decimal(meta.get(key))
    return default


def _decimal(raw: Any) -> Decimal:
    try:
        return Decimal(str(raw).replace(",", "."))
    except InvalidOperation:
        return Decimal("0")


def _number(value: Decimal | int | float) -> float:
    decimal = value if isinstance(value, Decimal) else Decimal(str(value))
    normalized = decimal.quantize(Decimal("0.001"))
    return float(normalized)
