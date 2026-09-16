"""
WorkOrderEvent — Semantic audit trail + idempotency.

Replaces django-simple-history with lightweight, queryable events.
Each mutation creates one event with incremental seq.

Event kinds include lifecycle transitions plus manual step/oven facts.

Canonical payload schemas per kind:

    planned:
        quantity: str       — planned quantity
        recipe: str         — recipe code
        output_sku: str     — produced SKU/ref
        target_date: str — planned date
        source_ref: str     — upstream source/request
        position_ref: str   — planned station/post
        operator_ref: str   — planned responsible actor

    adjusted:
        from: str           — previous quantity
        to: str             — new quantity
        reason: str         — adjustment reason

    planning_confirmed:
        quantity: str       — unchanged quantity acknowledged by the request
        result: str         — unchanged | consolidated
        attempt: dict       — immutable canonical request used for replay

    started:
        quantity: str       — quantity sent into production
        operator_ref: str   — who is producing (e.g. "user:joao")
        position_ref: str   — where (e.g. "producao")
        note: str           — optional note
        implicit: bool      — True if auto-started by finish

    finished:
        finished_qty: str   — actual output quantity
        planned_qty: str    — originally planned quantity
        started_qty: str    — quantity that entered production
        loss_qty: str       — waste/loss quantity
        output_sku: str     — produced SKU/ref
        target_date: str — production date
        source_ref: str     — upstream source/request
        position_ref: str   — station/post
        operator_ref: str   — responsible actor
        context: dict       — opaque caller-owned audit context

    oven_abandoned:
        run_id: int         — abandoned OvenRun primary key
        oven_ref: str       — oven/station snapshot
        transition: str     — finish | void | rearm | sweep
        reason: str         — why the open measurement became unusable

    shortage_overridden:
        action: str         — plan | finish | quick_finish
        reason: str         — required operator justification
        impact: dict        — frozen shortage/order impact snapshot
        work_order_rev: int — authoritative revision after the mutation

    quality_corrected:
        schema_version: int
        reason: str          — manager's required audit justification
        before_partition: list[dict]
        after_partition: list[dict]
        impact: dict         — stock/holds/communications reconciliation
        attempt: dict        — canonical request used for idempotent replay

    quality_reviewed:
        schema_version: int
        partition: list[dict] — effective QC facts confirmed by the manager
        attempt: dict         — canonical request used for idempotent replay

    voided:
        reason: str         — cancellation reason

WorkOrderItem provides the material ledger (requirement, consumption,
output, waste). Events are the semantic trail of what happened and why.
"""

from django.db import models
from django.utils.translation import gettext_lazy as _


class WorkOrderEvent(models.Model):
    """
    Immutable audit record for WorkOrder state transitions.

    - seq: incremental per WorkOrder (0, 1, 2, ...)
    - kind: planned | adjusted | started | finished | voided
    - payload: JSON with event-specific data (see module docstring for schemas)
    - idempotency_key: unique, prevents duplicate finish
    """

    class Kind(models.TextChoices):
        PLANNED = "planned", _("Planejado")
        PLANNING_CONFIRMED = "planning_confirmed", _("Planejamento confirmado")
        ADJUSTED = "adjusted", _("Ajustado")
        STARTED = "started", _("Iniciado")
        STEP_ADVANCED = "step_advanced", _("Passo avançado")
        OVEN_ARMED = "oven_armed", _("Enfornado")
        OVEN_CONCLUDED = "oven_concluded", _("Retirado do forno")
        OVEN_ABANDONED = "oven_abandoned", _("Medição de forno abandonada")
        SHORTAGE_OVERRIDDEN = "shortage_overridden", _("Falta sobreposta")
        FINISHED = "finished", _("Concluído")
        QUALITY_CORRECTED = "quality_corrected", _("Qualidade corrigida")
        QUALITY_REVIEWED = "quality_reviewed", _("Qualidade revisada")
        VOIDED = "voided", _("Cancelado")

    work_order = models.ForeignKey(
        "craftsman.WorkOrder",
        on_delete=models.CASCADE,
        related_name="events",
        verbose_name=_("Ordem"),
    )
    seq = models.PositiveIntegerField(
        verbose_name=_("Sequência"),
    )
    kind = models.CharField(
        max_length=20,
        choices=Kind.choices,
        verbose_name=_("Tipo"),
    )
    payload = models.JSONField(
        default=dict,
        blank=True,
        verbose_name=_("Dados"),
        help_text=_("Dados do evento. Schema por kind documentado no módulo."),
    )
    actor = models.CharField(
        max_length=100,
        blank=True,
        verbose_name=_("Ator"),
    )
    idempotency_key = models.CharField(
        max_length=200,
        unique=True,
        null=True,
        blank=True,
        verbose_name=_("Chave de Idempotência"),
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("Criado em"),
    )

    class Meta:
        db_table = "crafting_work_order_event"
        verbose_name = _("evento da ordem")
        verbose_name_plural = _("eventos da ordem")
        unique_together = [("work_order", "seq")]
        ordering = ["work_order", "seq"]

    def __str__(self) -> str:
        return f"#{self.seq} {self.kind} ({self.work_order_id})"
