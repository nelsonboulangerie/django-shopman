"""A cotação do dólar que a casa usou para dizer em reais o gasto com IA.

O custo da API de IA é em dólar e fica guardado assim (``AiInvocation.cost_usd_micros``).
O dono pensa em reais (decisão de 21/11/2026, DEV-2026-067): o B.I. converte pela PTAX de
venda do Banco Central do dia, e esta tabela guarda a cotação usada, para que o número em
reais de um dia passado não mude depois e para que se saiba de onde ele veio.

Um registro por dia do calendário. Fim de semana e feriado não têm PTAX: vale a do último
dia útil antes (``quoted_on``). Só se grava cotação final: a de um dia que já passou, ou a
do próprio dia depois de publicada. A de hoje antes da publicação (ainda a de ontem) é
provisória e não se grava.
"""

from __future__ import annotations

from django.db import models


class UsdBrlQuote(models.Model):
    date = models.DateField("dia", unique=True)
    quoted_on = models.DateField("dia da PTAX usada")
    sell_rate = models.DecimalField("PTAX de venda (R$ por US$)", max_digits=10, decimal_places=4)
    source = models.CharField("fonte", max_length=40, default="ptax-bcb")
    fetched_at = models.DateTimeField("buscada em", auto_now_add=True)

    class Meta:
        app_label = "shop"
        verbose_name = "cotação do dólar"
        verbose_name_plural = "cotações do dólar"
        ordering = ("-date",)

    def __str__(self) -> str:
        return f"{self.date:%d/%m/%Y}: R$ {self.sell_rate} (PTAX de {self.quoted_on:%d/%m})"
