"""
WorkOrderItem — Unified material ledger.

4 kinds in one table: requirement, consumption, output, waste.
All material traceability in pure SQL.

Example queries:
    -- Flour efficiency in WO-142
    SELECT kind, SUM(quantity) FROM crafting_work_order_item
    WHERE work_order_id = 142 AND item_ref = 'farinha' GROUP BY kind;

    -- Total baguette waste this month
    SELECT SUM(quantity) FROM crafting_work_order_item
    WHERE kind = 'waste' AND item_ref = 'baguete'
    AND recorded_at >= '2026-02-01';
"""

from django.db import models
from django.utils.translation import gettext_lazy as _


class WorkOrderItem(models.Model):
    """
    Lancamento no ledger de materiais.

    Cada item registra uma movimentacao (planejada ou real)
    associada a uma WorkOrder.
    """

    class Kind(models.TextChoices):
        REQUIREMENT = "requirement", _("Requisito")
        CONSUMPTION = "consumption", _("Consumo")
        OUTPUT = "output", _("Saida")
        WASTE = "waste", _("Perda")

    work_order = models.ForeignKey(
        "craftsman.WorkOrder",
        on_delete=models.CASCADE,
        related_name="items",
        verbose_name=_("Ordem"),
    )
    kind = models.CharField(
        max_length=15,
        choices=Kind.choices,
        verbose_name=_("Tipo"),
    )
    item_ref = models.CharField(
        max_length=100,
        verbose_name=_("Referencia"),
        help_text=_("SKU ou identificador do material"),
    )
    quantity = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        verbose_name=_("Quantidade"),
    )
    unit = models.CharField(
        max_length=20,
        blank=True,
        verbose_name=_("Unidade"),
    )
    recorded_at = models.DateTimeField(
        verbose_name=_("Registrado em"),
    )
    recorded_by = models.CharField(
        max_length=100,
        blank=True,
        verbose_name=_("Registrado por"),
    )
    meta = models.JSONField(
        default=dict,
        blank=True,
        verbose_name=_("Metadados"),
        help_text=_("lot, expires, reason, step, etc."),
    )
    # Partição de resultado (ADR-017): a fornada de 40 não produz "38" — produz
    # 32 a preço cheio, 8 com desconto, 3 de perda. Cada linha de OUTPUT/WASTE
    # pode carregar a natureza do seu grupo. O core NUNCA interpreta os valores:
    # são ponteiros string (ADR-004), validados na borda pelo framework — não
    # sabe que "minimal" vale menos que "standard" nem que um defeito veta.
    #
    # `quality_*` é um par de propósito (o quanto desviou e por quê); `grep
    # quality_` acha a feature inteira. `batch_ref` NÃO leva o prefixo porque
    # não é qualidade — é rastreabilidade, e existe mesmo em fornada perfeita.
    quality_grade_ref = models.CharField(
        max_length=32,
        blank=True,
        db_index=True,
        verbose_name=_("Grau de qualidade"),
    )
    quality_defect_ref = models.CharField(
        max_length=32,
        blank=True,
        db_index=True,
        verbose_name=_("Defeito"),
    )
    batch_ref = models.CharField(
        max_length=100,
        blank=True,
        db_index=True,
        verbose_name=_("Lote"),
    )

    class Meta:
        db_table = "crafting_work_order_item"
        verbose_name = _("item da ordem")
        verbose_name_plural = _("itens da ordem")
        indexes = [
            models.Index(fields=["work_order", "kind"]),
            models.Index(fields=["item_ref", "kind"]),
            models.Index(fields=["recorded_at"]),
            # O relatório de QC agrupa por grau/defeito num recorte de tempo
            # ("qual defeito custou mais este mês") — GROUP BY indexado.
            models.Index(fields=["quality_grade_ref", "recorded_at"]),
            models.Index(fields=["quality_defect_ref", "recorded_at"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(quantity__gt=0),
                name="craft_woitem_qty_positive",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.get_kind_display()}: {self.item_ref} ({self.quantity})"
