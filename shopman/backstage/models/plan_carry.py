"""O porquê que o B.I. leva ao plano (prévia ``bi-sobra4``, pino 3, "EXPLICAR NO LUGAR").

"Sobrou ou faltou ontem?" termina num gesto: **Levar ao plano do próximo sábado**.
O gesto não muda número nenhum do plano (quem sugere continua sendo a fórmula do
Craftsman, e quem decide continua sendo o padeiro). Ele grava, ao lado da
sugestão daquele dia, o fato que a leitura achou: "no sábado 03/10 acabou às
10:40, ~14 vendas perdidas". O Planejamento mostra a nota no "Por quê" da linha.

Uma linha por (dia do plano, SKU, dia lido): levar duas vezes o mesmo sábado
atualiza a nota em vez de repetir a frase. O fato vai em ``facts`` (JSON) e a
frase é montada na superfície, como no resto do B.I.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from shopman.utils.refs import RefField


class PlanCarryNote(models.Model):
    class Verdict(models.TextChoices):
        SHORT = "short", "faltou"
        OVER = "over", "sobrou"

    target_date = models.DateField("dia do plano", db_index=True)
    sku = RefField(ref_type="SKU", verbose_name="sku", max_length=100)
    source_day = models.DateField("dia lido no B.I.")
    verdict = models.CharField("veredito", max_length=8, choices=Verdict.choices)
    #: ``made``, ``sold``, ``leftover``, ``soldout_at``, ``lost_estimate`` (strings da
    #: leitura, como a projeção do B.I. as entrega).
    facts = models.JSONField("fatos", default=dict, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="levado por",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    created_at = models.DateTimeField("levado em", auto_now=True)

    class Meta:
        verbose_name = "nota do B.I. no plano"
        verbose_name_plural = "notas do B.I. no plano"
        ordering = ["target_date", "sku", "-source_day"]
        constraints = [
            models.UniqueConstraint(
                fields=["target_date", "sku", "source_day"],
                name="backstage_plan_carry_one_per_day",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.sku} em {self.target_date} ({self.get_verdict_display()} em {self.source_day})"
