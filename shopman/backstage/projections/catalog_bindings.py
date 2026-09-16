"""Revisão de evidências remotas e escolhas locais, sem aprovar publicação."""

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from urllib.parse import quote

from shopman.offerman.models import Product

from shopman.backstage.services import catalog_bindings as service
from shopman.shop.models import CatalogBinding, CatalogSnapshot
from shopman.shop.projections.types import Action


@dataclass(frozen=True)
class CatalogSnapshotSummary:
    id: int
    account_ref: str
    catalog_ref: str
    context: str
    captured_at: str
    imported_at: str
    sha256: str
    source: str
    item_count: int


@dataclass(frozen=True)
class CatalogProductOption:
    sku: str
    name: str


@dataclass(frozen=True)
class CatalogCurrentBinding:
    sku: str
    name: str
    actor: str
    confirmed_at: str
    revision: int
    snapshot_id: int


@dataclass(frozen=True)
class CatalogReviewItem:
    item_id: str
    product_ref: str
    category_ref: str
    category_name: str
    item_context_ref: str
    name: str
    description: str
    image_path: str
    status: str
    price: str
    external_code: str
    diagnostic: str
    notice: str
    candidates: tuple[CatalogProductOption, ...]
    binding: CatalogCurrentBinding | None
    base_revision: str
    can_bind: bool
    needs_review: bool
    blocked_reason: str
    binding_action: Action


@dataclass(frozen=True)
class CatalogBindingReviewProjection:
    channel_ref: str
    channel_name: str
    provider: str
    snapshots: tuple[CatalogSnapshotSummary, ...]
    selected_snapshot: CatalogSnapshotSummary | None
    products: tuple[CatalogProductOption, ...]
    items: tuple[CatalogReviewItem, ...]
    expected_actor_id: int | None
    notice: str
    import_action: Action


def _summary(snapshot):
    return CatalogSnapshotSummary(id=snapshot.pk, account_ref=snapshot.account_ref,
        catalog_ref=snapshot.catalog_ref, context=snapshot.context,
        captured_at=snapshot.captured_at.isoformat(), imported_at=snapshot.imported_at.isoformat(),
        sha256=snapshot.sha256, source=snapshot.source, item_count=snapshot.item_count)


def _text(value):
    return value if isinstance(value, str) else ""


def _price(value):
    if isinstance(value, bool) or not isinstance(value, (Decimal, int, str)):
        return ""
    try:
        number = Decimal(value)
        if not number.is_finite():
            return ""
    except InvalidOperation:
        return ""
    return str(value)


def build_catalog_binding_review(*, channel_ref, snapshot_id=None, user=None):
    channel = service._channel(channel_ref)
    authorized = bool(user and user.is_active and user.is_staff and user.has_perm("shop.manage_catalog"))
    actor_id = getattr(user, "pk", None)
    base_path = f"/api/v1/backstage/catalog/channels/{quote(channel.ref, safe='')}/"
    snapshots = list(CatalogSnapshot.objects.filter(channel=channel).defer("raw_json"))
    snapshot = (next((row for row in snapshots if row.pk == snapshot_id), None)
                if snapshot_id is not None else (snapshots[0] if snapshots else None))
    if snapshot_id is not None and snapshot is None:
        raise service.CatalogBindingError("Snapshot não pertence ao canal selecionado.")
    products = list(Product.objects.only("pk", "sku", "name").order_by("sku"))
    options = {product.sku: CatalogProductOption(sku=product.sku, name=product.name) for product in products}
    items = []
    if snapshot:
        if snapshot.provider != "ifood":
            raise service.CatalogBindingError("Não há parser para este provedor.")
        bindings = {binding.resource_id: binding for binding in CatalogBinding.objects.filter(
            **service.scope(snapshot)).select_related("product", "confirmed_by")}
        for row in service.review_rows(snapshot, products):
            identity = row["identity"]
            binding = bindings.get(identity["item_id"])
            blocked = service.binding_block(row)
            if binding and binding.channel_id != channel.pk:
                blocked = "Este recurso já está vinculado em outro canal; confira o escopo."
            if not authorized:
                blocked = "Identifique uma pessoa com permissão para editar o catálogo."
            product = row["remote"]["product"] or {}
            effective = row["remote"]["effective_context"] or {}
            price = effective.get("price")
            price = price.get("value") if isinstance(price, dict) else None
            revision = service.binding_revision(snapshot, identity["item_id"], binding)
            items.append(CatalogReviewItem(item_id=identity["item_id"], product_ref=identity["product_id"],
                category_ref=identity["category_id"], category_name=identity["category_name"], item_context_ref=_text(service.item_context_ref(row)),
                name=_text(product.get("name")), description=_text(product.get("description")),
                image_path=_text(product.get("imagePath")), status=_text(effective.get("status")), price=_price(price),
                external_code=identity["external_code"], diagnostic=identity["status"], notice=identity["notice"],
                candidates=tuple(options[sku] for sku in identity["candidate_skus"] if sku in options),
                binding=None if not binding else CatalogCurrentBinding(sku=binding.product.sku, name=binding.product.name,
                    actor=binding.confirmed_by.get_username(), confirmed_at=binding.confirmed_at.isoformat(), revision=binding.revision,
                    snapshot_id=binding.snapshot_id),
                base_revision=revision, can_bind=not blocked, needs_review=not binding or binding.snapshot_id != snapshot.pk, blocked_reason=blocked,
                binding_action=Action(ref="catalog.binding.confirm", kind="mutation", label="Confirmar vínculo local",
                    enabled=not blocked, reason=blocked, href=base_path + "bindings/", method="POST", idempotency="required",
                    payload_schema={"expected_actor_id": actor_id, "snapshot_id": snapshot.pk,
                                    "item_id": identity["item_id"], "base_revision": revision})))
    return CatalogBindingReviewProjection(channel_ref=channel.ref, channel_name=channel.name or channel.ref,
        provider="ifood", snapshots=tuple(_summary(row) for row in snapshots), selected_snapshot=_summary(snapshot) if snapshot else None,
        products=tuple(options.values()), items=tuple(items), expected_actor_id=actor_id,
        notice="Vínculo somente local. Não altera produtos ou o iFood, não aprova publicação nem atesta a origem do arquivo.",
        import_action=Action(ref="catalog.snapshot.import", kind="mutation", label="Importar evidência",
            enabled=authorized, reason="" if authorized else "Identifique uma pessoa com permissão para editar o catálogo.",
            href=base_path + "snapshots/", method="POST", idempotency="required", payload_schema={"expected_actor_id": actor_id,
                "base_revision": service.import_revision(channel, user) if user else ""}))
