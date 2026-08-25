"""PurchaseProjection — read model for the Compras operator app.

Composes Buyman's upstream master data, Stockman's ledger, and Craftsman's
recipes into the contract consumed by ``surfaces/purchase-nuxt``. The domain
packages stay agnostic: this file is a Backstage projection, not Core behavior.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from django.apps import apps
from django.db.models import Sum
from django.utils import timezone

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
class ReceiptLineProjection:
    id: str
    materialSku: str
    conversionId: str | None
    purchaseQty: float
    costInput: str
    expiryDate: str
    lineNote: str
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

    stock_on_hand = _stock_on_hand_map(skus)
    daily_use = _daily_use_map(skus)
    recipes = _recipes_map(skus)
    last_delivery = _last_delivery_map(supplier_refs)

    suppliers = tuple(_supplier_projection(supplier, last_delivery.get(supplier.ref, "")) for supplier in supplier_rows)
    materials = tuple(
        _material_projection(
            material,
            stock_on_hand=stock_on_hand.get(material.sku, Decimal("0")),
            daily_use=daily_use.get(material.sku, Decimal("0")),
            recipes=recipes.get(material.sku, ()),
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


def _material_projection(material, *, stock_on_hand: Decimal, daily_use: Decimal, recipes: tuple[str, ...]) -> MaterialProjection:
    meta = _purchase_meta(material)
    min_stock = _meta_decimal(meta, "min_stock", "minStock", default=None)
    if min_stock is None:
        min_stock = daily_use * Decimal("3") if daily_use > 0 else Decimal("0")
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
    )


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
    return ActiveReceiptProjection(
        mode=str(data.get("mode") or "invoice"),
        supplierRef=str(data.get("supplierRef") or data.get("supplier_ref") or default_supplier_ref),
        invoiceInput=str(data.get("invoiceInput") or data.get("invoice_input") or ""),
        note=str(data.get("note") or ""),
        lines=tuple(_receipt_line_projection(line) for line in data.get("lines") or ()),
    )


def _receipt_line_projection(line: dict[str, Any]) -> ReceiptLineProjection:
    return ReceiptLineProjection(
        id=str(line.get("id") or ""),
        materialSku=str(line.get("materialSku") or line.get("material_sku") or ""),
        conversionId=(
            str(line.get("conversionId") or line.get("conversion_id"))
            if line.get("conversionId") or line.get("conversion_id")
            else None
        ),
        purchaseQty=_number(_decimal(line.get("purchaseQty", line.get("purchase_qty", 0)))),
        costInput=str(line.get("costInput") or line.get("cost_input") or ""),
        expiryDate=str(line.get("expiryDate") or line.get("expiry_date") or ""),
        lineNote=str(line.get("lineNote") or line.get("line_note") or line.get("note") or ""),
        checked=bool(line.get("checked")),
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
