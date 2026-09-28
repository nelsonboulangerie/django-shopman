"""Read model público e descartável do cardápio estrutural."""

from __future__ import annotations

import uuid

from django.db import models


def new_catalog_epoch() -> str:
    return f"e_{uuid.uuid4().hex}"


class CatalogStructureHead(models.Model):
    """Cabeça materializada do snapshot estrutural público.

    O banco continua sendo a autoridade. Esta linha é uma projeção reconstruível;
    ``sequence`` só avança quando o estado estrutural canonicalizado muda.
    """

    channel_ref = models.CharField(max_length=32, unique=True)
    stream_id = models.CharField(max_length=128)
    epoch = models.CharField(max_length=64, default=new_catalog_epoch)
    sequence = models.PositiveBigIntegerField(default=0)
    state_token = models.CharField(max_length=128, blank=True)
    state_digest = models.CharField(max_length=80, blank=True)
    etag = models.CharField(max_length=96, blank=True)
    message = models.JSONField(default=dict)
    dirty = models.BooleanField(default=True)
    built_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "cabeça estrutural do cardápio"
        verbose_name_plural = "cabeças estruturais do cardápio"

    def __str__(self) -> str:
        return f"{self.channel_ref}:{self.epoch}:{self.sequence}"
