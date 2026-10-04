"""Contagem de volumes da NF em conferência ("Contei N volumes").

O rascunho da conferência mora no cliente; a contagem de volumes é a exceção,
porque é o único ATO FÍSICO da doca: abrir a mesma NF em outro dispositivo (o
tablet da doca e, depois, o celular de quem confere) não pode voltar a pedir que
alguém conte as caixas de novo (L7, SUITE-UX-FUNCTION-PLAN). Uma linha por chave
de acesso; some quando a entrada é registrada.
"""

from __future__ import annotations

from django.db import models


class ReceiptVolumeCount(models.Model):
    invoice_key = models.CharField("chave da NF", max_length=44, unique=True)
    counted = models.PositiveSmallIntegerField("volumes contados")
    counted_by = models.CharField("contado por", max_length=150, blank=True)
    counted_at = models.DateTimeField("contado em", auto_now=True)

    class Meta:
        verbose_name = "contagem de volumes da NF"
        verbose_name_plural = "contagens de volumes da NF"

    def __str__(self) -> str:
        return f"{self.invoice_key[-4:]}: {self.counted}"
