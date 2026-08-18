"""Per-(product, channel) catalog sync state.

Records the outcome of the last projection of a SKU to each external channel
(iFood, Meta, Google, WhatsApp, TikTok): status, when, external id, error. Fine
and queryable — the source of truth the operator matrix reads for a per-cell
badge, replacing the bare ``Listing.projection_metadata['last_projected_skus']``.

Written by the projection handler/adapters; read by the backstage catalog
sync-status projection.
"""

from __future__ import annotations

from django.db import models
from shopman.utils.refs import RefField


class SyncStatus(models.TextChoices):
    SYNCED = "synced", "Sincronizado"
    PENDING = "pending", "Pendente"
    ERROR = "error", "Erro"
    RETRACTED = "retracted", "Retirado"
    SKIPPED = "skipped", "Ignorado"


class CatalogSyncState(models.Model):
    sku = RefField(ref_type="SKU", max_length=100, db_index=True)
    # Platform / projection channel ref (== listing_ref): ifood, meta, google, whatsapp, tiktok.
    # Ref do canal — a mesma chave para transacional (`ifood`) e exibição
    # (`meta-catalog`). Uma pergunta, uma chave (ADR-018).
    channel_ref = models.CharField(max_length=32, db_index=True)
    # Id of the item on the external channel (e.g. Meta retailer_id, iFood item uuid).
    external_id = models.CharField(max_length=200, blank=True)
    status = models.CharField(max_length=16, choices=SyncStatus.choices, default=SyncStatus.PENDING)
    last_synced_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True)
    # Hash of the last payload pushed — lets adapters skip an identical re-push.
    last_payload_hash = models.CharField(max_length=64, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "shop"
        verbose_name = "estado de sync do catálogo"
        verbose_name_plural = "estados de sync do catálogo"
        constraints = [
            models.UniqueConstraint(fields=["sku", "channel_ref"], name="uniq_catalog_sync_sku_channel"),
        ]
        indexes = [models.Index(fields=["channel_ref", "status"])]

    def __str__(self) -> str:
        return f"{self.sku}@{self.channel_ref}: {self.status}"
