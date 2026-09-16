"""Evidências imutáveis e vínculos locais de recursos de catálogos externos."""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class _SnapshotQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise ValidationError("Snapshots de catálogo são imutáveis.")

    def delete(self):
        raise ValidationError("Snapshots de catálogo não podem ser removidos.")


class CatalogSnapshot(models.Model):
    channel = models.ForeignKey("shop.Channel", on_delete=models.PROTECT, related_name="catalog_snapshots")
    provider = models.CharField(max_length=32)
    account_ref = models.CharField(max_length=128)
    catalog_ref = models.CharField(max_length=128)
    context = models.CharField(max_length=128)
    captured_at = models.DateTimeField()
    imported_at = models.DateTimeField(default=timezone.now, editable=False)
    imported_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="catalog_snapshots")
    sha256 = models.CharField(max_length=64)
    raw_json = models.TextField()
    source = models.CharField(max_length=32)
    item_count = models.PositiveIntegerField()
    objects = _SnapshotQuerySet.as_manager()

    class Meta:
        app_label = "shop"
        ordering = ("-imported_at", "-pk")
        indexes = [models.Index(fields=["channel", "provider", "-imported_at"], name="catalog_snapshot_channel_idx")]

    def save(self, *args, **kwargs):
        if self.pk or not self._state.adding:
            raise ValidationError("Snapshots de catálogo são imutáveis.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Snapshots de catálogo não podem ser removidos.")

    def __str__(self):
        return f"{self.provider}:{self.catalog_ref}:{self.sha256[:12]}"


class CatalogBinding(models.Model):
    channel = models.ForeignKey("shop.Channel", on_delete=models.PROTECT, related_name="catalog_bindings")
    product = models.ForeignKey("offerman.Product", on_delete=models.PROTECT, related_name="catalog_bindings")
    provider = models.CharField(max_length=32)
    account_ref = models.CharField(max_length=128)
    catalog_ref = models.CharField(max_length=128)
    context = models.CharField(max_length=128)
    resource_id = models.CharField(max_length=256)
    external_product_ref = models.CharField(max_length=256)
    category_ref = models.CharField(max_length=256)
    item_context_ref = models.CharField(max_length=256, blank=True)
    snapshot = models.ForeignKey(CatalogSnapshot, on_delete=models.PROTECT, related_name="bindings")
    confirmed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="catalog_bindings")
    confirmed_at = models.DateTimeField(default=timezone.now)
    revision = models.PositiveIntegerField(default=1)

    class Meta:
        app_label = "shop"
        constraints = [models.UniqueConstraint(
            fields=["provider", "account_ref", "catalog_ref", "context", "resource_id"],
            name="unique_catalog_remote_resource",
        )]

    def __str__(self):
        return f"{self.provider}:{self.resource_id} → {self.product_id}"
