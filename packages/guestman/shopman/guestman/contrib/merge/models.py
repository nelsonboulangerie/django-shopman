"""MergeAudit — audit trail + undo snapshot for customer merges."""

from __future__ import annotations

import uuid

from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class MergeStatus(models.TextChoices):
    COMPLETED = "completed", _("Unificada")
    REVERTED = "reverted", _("Desfeita")


class MergeAudit(models.Model):
    """
    Audit trail for customer merges.

    Stores a snapshot of what was migrated so the merge can be
    partially reverted within the UNDO_WINDOW.
    """

    UNDO_WINDOW_HOURS = 24

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Who was merged
    source_ref = models.CharField(_("cadastro absorvido"), max_length=50)
    target_ref = models.CharField(_("cadastro que ficou"), max_length=50)
    source_id = models.UUIDField(_("id do cadastro absorvido"))
    target_id = models.UUIDField(_("id do cadastro que ficou"))

    # Audit info
    actor = models.CharField(_("quem unificou"), max_length=200, blank=True)
    evidence = models.JSONField(_("justificativa"), default=dict)
    status = models.CharField(
        _("situação"),
        max_length=20,
        choices=MergeStatus.choices,
        default=MergeStatus.COMPLETED,
    )

    # Snapshot of migrated PKs (for undo)
    snapshot = models.JSONField(
        _("retrato para desfazer"),
        default=dict,
        help_text=_("O que foi movido, por categoria — é daqui que o desfazer devolve."),
    )

    # Counts (denormalized for quick reference)
    migrated_contact_points = models.PositiveIntegerField(_("contatos migrados"), default=0)
    migrated_external_identities = models.PositiveIntegerField(_("identidades externas migradas"), default=0)
    migrated_identifiers = models.PositiveIntegerField(_("identificadores migrados"), default=0)
    migrated_addresses = models.PositiveIntegerField(_("endereços migrados"), default=0)
    migrated_preferences = models.PositiveIntegerField(_("preferências migradas"), default=0)
    migrated_consents = models.PositiveIntegerField(_("consentimentos migrados"), default=0)
    migrated_timeline_events = models.PositiveIntegerField(_("eventos de histórico migrados"), default=0)
    loyalty_merged = models.BooleanField(_("fidelidade somada"), default=False)

    # Timestamps
    merged_at = models.DateTimeField(_("unificado em"), default=timezone.now)
    reverted_at = models.DateTimeField(_("desfeito em"), null=True, blank=True)
    reverted_by = models.CharField(_("quem desfez"), max_length=200, blank=True)

    class Meta:
        verbose_name = _("unificação de cadastros")
        verbose_name_plural = _("unificações de cadastros")
        ordering = ["-merged_at"]
        indexes = [
            models.Index(fields=["source_ref"], name="customers_merge_src_ref"),
            models.Index(fields=["target_ref"], name="customers_merge_tgt_ref"),
        ]

    def __str__(self) -> str:
        return f"Merge {self.source_ref} → {self.target_ref} ({self.status})"

    @property
    def can_undo(self) -> bool:
        """Check if merge is within the undo window."""
        if self.status != MergeStatus.COMPLETED:
            return False
        from datetime import timedelta

        deadline = self.merged_at + timedelta(hours=self.UNDO_WINDOW_HOURS)
        return timezone.now() < deadline

    @property
    def undo_deadline(self):
        """When the undo window expires."""
        from datetime import timedelta

        return self.merged_at + timedelta(hours=self.UNDO_WINDOW_HOURS)
