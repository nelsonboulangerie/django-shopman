"""Adapter conservador do snapshot público Continuum 0.2 do cardápio."""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC
from typing import Any

from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.utils import timezone

from shopman.storefront.models import CatalogStructureHead

PROTOCOL_VERSION = "0.2"
STREAM_ID = "s_shopman_storefront_catalog_structure_v1"
PROJECTION = "shopman.storefront.catalog_structure"
PARTITION = "p_public_web"
STREAM_SCHEMA = "urn:shopman:schema:storefront:catalog-structure:v1"
DATA_SCHEMA = "urn:shopman:schema:continuum:v0.2:snapshot"
SOURCE = "urn:shopman:storefront:catalog-structure"
CACHE_PREFIX = "storefront:continuum:v0.2:catalog-structure"


@dataclass(frozen=True)
class ShadowComparison:
    equal: bool
    cache_status: str
    snapshot_bytes: int
    head: CatalogStructureHead


def continuum_settings() -> dict[str, Any]:
    return dict(getattr(settings, "SHOPMAN_CONTINUUM", {}))


def candidate_enabled() -> bool:
    config = continuum_settings()
    return bool(config.get("catalog_snapshot_enabled")) and not bool(config.get("kill_switch"))


def shadow_enabled() -> bool:
    config = continuum_settings()
    return bool(config.get("catalog_shadow_enabled")) and not bool(config.get("kill_switch"))


def limits() -> dict[str, int]:
    return dict(continuum_settings().get("limits") or {})


def canonical_json(value: Any) -> bytes:
    """Canonicalização suficiente para este schema I-JSON sem floats."""
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def sha256_digest(value: Any) -> str:
    raw = hashlib.sha256(canonical_json(value)).digest()
    return "sha256-" + base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def catalog_structure_state_from_projection(data: dict[str, Any]) -> dict[str, Any]:
    """Extrai a estrutura pública de uma projeção canônica já calculada."""
    item_fields = (
        "sku",
        "slug",
        "name",
        "short_description",
        "image_url",
        "category",
        "tags",
        "search_terms",
        "dietary_info",
        "is_new",
        "unit_weight_label",
        "allergens",
        "category_color",
        "category_icon",
    )
    items = {
        item["sku"]: {field: item.get(field) for field in item_fields}
        for item in data.get("items", [])
    }
    sections = []
    for section in data.get("sections", []):
        if section.get("is_dynamic"):
            continue
        sections.append({
            "ref": section.get("ref") or "",
            "label": section.get("label") or "",
            "icon": section.get("icon") or "",
            "description": section.get("description") or "",
            "category": section.get("category"),
            "skus": [item["sku"] for item in section.get("items", [])],
        })
    return {
        "items": items,
        "item_order": [item["sku"] for item in data.get("items", [])],
        "categories": data.get("categories", []),
        "sections": sections,
        "empty_state": data.get("empty_state"),
        "search_empty_state": data.get("search_empty_state"),
        "has_items": bool(data.get("has_items")),
    }


def catalog_structure_state(catalog) -> dict[str, Any]:
    """Extrai só estrutura pública do construtor canônico do cardápio."""
    from shopman.storefront.api.projections import projection_data

    return catalog_structure_state_from_projection(projection_data(catalog))


def _sequence(value: int) -> str:
    return f"{value:020d}"


def _build_message(*, head: CatalogStructureHead, state: dict[str, Any]) -> dict[str, Any]:
    now = timezone.now().astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    return {
        "specversion": "1.0",
        "id": f"evt_{uuid.uuid4().hex}",
        "source": SOURCE,
        "type": "continuum.projection.snapshot.v0.2",
        "subject": f"stream/{STREAM_ID}",
        "time": now,
        "datacontenttype": "application/json",
        "dataschema": DATA_SCHEMA,
        "data": {
            "protocol_version": PROTOCOL_VERSION,
            "kind": "snapshot",
            "stream": {
                "id": STREAM_ID,
                "projection": PROJECTION,
                "partition": PARTITION,
                "schema": STREAM_SCHEMA,
                "classification": "public",
            },
            "target": {
                "cursor": {
                    "epoch": head.epoch,
                    "sequence": _sequence(head.sequence),
                },
                "state_token": head.state_token,
                "state_digest": head.state_digest,
            },
            "freshness": {
                "fresh_for_ms": int(continuum_settings().get("fresh_for_ms", 30_000)),
                "stale_if_error_ms": int(continuum_settings().get("stale_if_error_ms", 120_000)),
                "age_ms": 0,
            },
            "state": state,
            "reset_reason": "bootstrap",
        },
    }


def _cache_key(head: CatalogStructureHead) -> str:
    return f"{CACHE_PREFIX}:{head.channel_ref}:{head.epoch}:{head.sequence}:{head.state_token}"


def head_age_ms(head: CatalogStructureHead) -> int:
    watermark = head.verified_at or head.built_at
    if watermark is None:
        return 0
    return max(
        0,
        int((timezone.now().astimezone(UTC) - watermark.astimezone(UTC)).total_seconds() * 1000),
    )


def reconciliation_due(head: CatalogStructureHead) -> bool:
    """Return whether the disposable head must be checked against canonical state.

    Signals remain the fast path, but cannot be the durability boundary: a process
    can die after the source commit and before ``on_commit`` runs, and bulk writers
    can bypass model signals altogether. A bounded canonical revalidation makes
    either failure self-healing without putting the full catalog builder on every
    snapshot request.
    """
    config = continuum_settings()
    # HTTP freshness and origin reconciliation are different clocks. The edge
    # may revalidate every 30s so clients learn about a dirty head quickly,
    # while the expensive canonical safety scan runs at a calmer cadence. The
    # previous ``min(..., fresh_for_ms)`` forced a 96-query catalog rebuild on
    # every cache revalidation even when signals had kept the head current.
    configured = int(config.get("reconcile_after_ms", 300_000))
    return head.verified_at is None or configured <= 0 or head_age_ms(head) >= configured


def rendered_message(head: CatalogStructureHead) -> tuple[bytes, str]:
    key = _cache_key(head)
    cached = cache.get(key)
    if isinstance(cached, bytes):
        return cached, "hit"
    body = canonical_json(head.message)
    cache.set(key, body, timeout=int(continuum_settings().get("snapshot_cache_seconds", 300)))
    return body, "miss"


def materialize_catalog_structure(
    catalog=None,
    *,
    channel_ref: str,
    state: dict[str, Any] | None = None,
) -> CatalogStructureHead:
    if state is None:
        if catalog is None:
            raise ValueError("catalog_or_state_required")
        state = catalog_structure_state(catalog)
    digest = sha256_digest(state)
    verified_at = timezone.now()
    with transaction.atomic():
        head, _ = CatalogStructureHead.objects.select_for_update().get_or_create(
            channel_ref=channel_ref,
            defaults={"stream_id": STREAM_ID},
        )
        if head.state_digest == digest and head.message:
            head.dirty = False
            head.verified_at = verified_at
            head.save(update_fields=["dirty", "verified_at", "updated_at"])
            return head

        head.stream_id = STREAM_ID
        head.sequence += 1
        head.state_token = f"t_{secrets.token_urlsafe(24)}"
        head.state_digest = digest
        head.built_at = timezone.now()
        head.verified_at = verified_at
        head.dirty = False
        head.message = _build_message(head=head, state=state)
        body = canonical_json(head.message)
        head.etag = '"sha256-' + base64.urlsafe_b64encode(
            hashlib.sha256(body).digest()
        ).decode("ascii").rstrip("=") + '"'
        head.save()
        return head


def current_or_build_head(*, channel_ref: str) -> tuple[CatalogStructureHead, str]:
    head = CatalogStructureHead.objects.filter(channel_ref=channel_ref).first()
    if head is not None and not head.dirty and head.message and not reconciliation_due(head):
        return head, "head"

    from shopman.storefront.presentation import build_catalog

    catalog = build_catalog(channel_ref=channel_ref, request=None)
    status = "reconcile" if head is not None and not head.dirty and head.message else "rebuild"
    return materialize_catalog_structure(catalog, channel_ref=channel_ref), status


def compare_shadow(projection: dict[str, Any], *, channel_ref: str) -> ShadowComparison:
    """Compara sem recalcular a projeção que o menu acabou de produzir."""
    state = catalog_structure_state_from_projection(projection)
    digest = sha256_digest(state)
    head = CatalogStructureHead.objects.filter(channel_ref=channel_ref).first()
    if head is None or head.dirty or not head.message:
        head = materialize_catalog_structure(channel_ref=channel_ref, state=state)
        body, body_cache_status = rendered_message(head)
        return ShadowComparison(
            equal=True,
            cache_status=f"rebuild:{body_cache_status}",
            snapshot_bytes=len(body),
            head=head,
        )
    equal = secrets.compare_digest(head.state_digest, digest)
    if not equal:
        head = materialize_catalog_structure(channel_ref=channel_ref, state=state)
    body, body_cache_status = rendered_message(head)
    return ShadowComparison(
        equal=equal,
        cache_status=f"{'hit' if equal else 'diverged_rebuild'}:{body_cache_status}",
        snapshot_bytes=len(body),
        head=head,
    )


def mark_catalog_structure_dirty() -> None:
    CatalogStructureHead.objects.filter(channel_ref="web").update(dirty=True)


def schedule_catalog_structure_dirty(sender=None, **kwargs) -> None:
    del sender, kwargs
    transaction.on_commit(mark_catalog_structure_dirty, robust=True)


def json_shape(value: Any) -> tuple[int, int]:
    """Retorna ``(nodes, depth)`` com a convenção normativa da spec."""
    nodes = 1
    depth = 1
    if isinstance(value, dict):
        child_shapes = [json_shape(item) for item in value.values()]
    elif isinstance(value, list):
        child_shapes = [json_shape(item) for item in value]
    else:
        child_shapes = []
    if child_shapes:
        nodes += sum(child_nodes for child_nodes, _ in child_shapes)
        depth += max(child_depth for _, child_depth in child_shapes)
    return nodes, depth


def validate_message_limits(message: dict[str, Any], body: bytes) -> None:
    configured = limits()
    nodes, depth = json_shape(message)
    checks = {
        "max_decoded_response_bytes": len(body),
        "max_result_bytes": len(canonical_json(message["data"]["state"])),
        "max_json_nodes": nodes,
        "max_json_depth": depth,
    }
    for name, actual in checks.items():
        maximum = int(configured.get(name, 0))
        if maximum <= 0 or actual > maximum:
            raise ValueError(f"continuum_limit:{name}")
