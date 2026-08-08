"""Catalog sync-state service — record and read per-(sku, channel) sync outcomes.

The projection handler/adapters call :func:`record_sync` at the end of every
project/retract; the backstage catalog surface reads :func:`sync_states_for` to
render a per-cell status badge and a "sincronizar agora" action.
"""

from __future__ import annotations

from django.utils import timezone

from shopman.shop.models import CatalogSyncState, SyncStatus

_TERMINAL_OK = {SyncStatus.SYNCED, SyncStatus.RETRACTED}


def record_sync(
    sku: str,
    channel_ref: str,
    *,
    status: str,
    external_id: str | None = None,
    error: str = "",
    payload_hash: str = "",
) -> CatalogSyncState:
    """Upsert the sync state for ``(sku, channel_ref)``.

    ``synced``/``retracted`` stamp ``last_synced_at``; ``error`` keeps the message;
    ``pending`` (e.g. rate-limited) clears the error. ``external_id`` is only
    overwritten when provided (adapters may not always know it).
    """
    defaults: dict = {
        "status": status,
        "last_error": error or "",
        "last_payload_hash": payload_hash or "",
    }
    if status in _TERMINAL_OK:
        defaults["last_synced_at"] = timezone.now()
    if external_id is not None:
        defaults["external_id"] = external_id
    obj, _created = CatalogSyncState.objects.update_or_create(
        sku=sku, channel_ref=channel_ref, defaults=defaults,
    )
    return obj


def sync_states_for(
    skus: list[str] | None = None,
    *,
    channel_ref: str | None = None,
) -> list[CatalogSyncState]:
    """Return sync states, optionally filtered by SKUs and/or channel_ref."""
    qs = CatalogSyncState.objects.all()
    if skus is not None:
        qs = qs.filter(sku__in=list(skus))
    if channel_ref:
        qs = qs.filter(channel_ref=channel_ref)
    return list(qs.order_by("sku", "channel_ref"))


def sync_status_map(
    skus: list[str] | None = None,
    *,
    channel_ref: str | None = None,
) -> dict[str, dict[str, dict]]:
    """``{sku: {channel_ref: {status, last_synced_at, external_id, error}}}`` for the matrix."""
    out: dict[str, dict[str, dict]] = {}
    for state in sync_states_for(skus, channel_ref=channel_ref):
        out.setdefault(state.sku, {})[state.channel_ref] = {
            "status": state.status,
            "last_synced_at": state.last_synced_at.isoformat() if state.last_synced_at else None,
            "external_id": state.external_id or "",
            "error": state.last_error or "",
        }
    return out
