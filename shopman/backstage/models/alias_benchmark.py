"""O placar do de-para de produto, guardado para a casa ler no Admin (BI-JEV-PILOT).

Só agregado: quantos cada concorrente acertou, quantos aceitaria sozinho e
quantos desses errados, tempo e custo. Nomes de produto não entram — o caso a
caso continua no ``--csv`` do comando, para quem roda à mão.
"""

from __future__ import annotations

from django.db import models


class AliasBenchmarkReport(models.Model):
    created_at = models.DateTimeField("medido em", auto_now_add=True)
    source = models.CharField("origem", max_length=16, db_index=True)
    cases = models.PositiveIntegerField("de-paras confirmados")
    contenders = models.CharField("concorrentes", max_length=240)
    skipped = models.TextField("fora do placar", blank=True)
    report = models.TextField("placar")

    class Meta:
        verbose_name = "placar do de-para"
        verbose_name_plural = "placares do de-para"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Placar de {self.created_at:%d/%m/%Y %H:%M}"
