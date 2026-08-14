"""OvenRun — o fato temporal do forno (ADR-021 §4, BI-PLAN §4).

O timer do kiosk é só a ferramenta de UI da declaração: armar = enfornou,
Concluir = retirou. O servidor carimba os dois momentos no recebimento, como
``started_at``/``finished_at`` da WorkOrder — sem relógio de cliente. Pausa e
``+N`` do countdown são UX local e não medem; run aberto sem Concluir vira
``abandoned`` (sem resposta, sem medição). O QC segue dono do fato comercial
(partição/lote); este model é dono do fato temporal.
"""

from __future__ import annotations

from django.db import models
from django.utils import timezone


class OvenRun(models.Model):
    STATUS_CHOICES = [
        ("open", "no forno"),
        ("concluded", "concluída"),
        ("abandoned", "sem medição"),
    ]

    work_order_ref = models.CharField(
        "ordem de produção", max_length=64, db_index=True,
        help_text="WorkOrder.ref (string ref, nunca FK cross-domain — ADR-004).",
    )
    oven_ref = models.CharField(
        "forno", max_length=64, blank=True,
        help_text="Snapshot de WorkOrder.position_ref no momento do arm.",
    )
    operator_ref = models.CharField("operador", max_length=64, blank=True)
    planned_seconds = models.PositiveIntegerField(
        "duração armada (s)",
        help_text="Duração do timer no arm. Referência, não medição.",
    )
    armed_at = models.DateTimeField("enfornou em", default=timezone.now, db_index=True)
    concluded_at = models.DateTimeField(
        "retirou em", null=True, blank=True,
        help_text="Só o Concluir declarado escreve aqui.",
    )
    status = models.CharField(
        "status", max_length=20, choices=STATUS_CHOICES, default="open", db_index=True,
    )
    metadata = models.JSONField("metadata", default=dict, blank=True)

    class Meta:
        verbose_name = "medição de forno"
        verbose_name_plural = "medições de forno"
        ordering = ["-armed_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["work_order_ref"],
                condition=models.Q(status="open"),
                name="backstage_ovenrun_one_open_per_wo",
            ),
            models.CheckConstraint(
                condition=~models.Q(status="concluded") | models.Q(concluded_at__isnull=False),
                name="backstage_ovenrun_concluded_has_timestamp",
            ),
        ]
        indexes = [
            models.Index(fields=["status", "armed_at"], name="backstage_ov_status_armed_idx"),
        ]

    def __str__(self):
        return f"OvenRun {self.work_order_ref} ({self.get_status_display()})"

    @property
    def elapsed_seconds(self) -> int | None:
        """Tempo real de forno. Só existe quando o Concluir foi declarado."""
        if self.status != "concluded" or self.concluded_at is None:
            return None
        return int((self.concluded_at - self.armed_at).total_seconds())
