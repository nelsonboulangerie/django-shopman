"""A série diária de vendas, materializada — a camada de leitura do B.I. (P3).

Uma linha por dia **coberto pela atualização**, com a venda do dia já
conciliada pela camada canônica (o dia nativo vence). É a única tabela
derivada do v1, e existe por três motivos, nenhum deles "performance":

- a projeção e a previsão de troco leem a mesma série dezenas de vezes por
  request, e um número que muda entre duas leituras do mesmo request é o pior
  defeito de um B.I.;
- os alarmes do roadmap (baseline do mesmo dia da semana; "dia nativo apagou
  histórico") precisam de um lugar persistido para comparar e declarar;
- a materialização é o formato que a ADR-021 §3 prevê quando o gatilho de
  custo disparar — nasce agora com motivo, e o resto do B.I. segue calculando
  na hora até lá.

**Presença é cobertura, ausência é "ninguém calculou".** Dia sem venda entra
com ``orders=0`` (e ``source`` vazio); é isso que permite ao leitor distinguir
"dia vazio" de "dia não materializado" e cair para o cálculo ao vivo em vez de
inventar um zero. **Recomputável do zero** em segundos (``refresh_bi_daily_series
--all``): nada aqui é fonte de verdade, tudo é derivado do que os ledgers e o
histórico já guardam.
"""

from __future__ import annotations

from django.db import models


class DailySalesFact(models.Model):
    date = models.DateField("dia", unique=True)
    source = models.CharField(
        "origem", max_length=16, blank=True,
        help_text="Quem respondeu pelo dia: shopman, yooga, seed… Vazio quando o dia não teve venda.",
    )
    revenue_q = models.BigIntegerField("faturamento (centavos)", default=0)
    orders = models.PositiveIntegerField("vendas", default=0)
    cash_orders = models.PositiveIntegerField(
        "vendas com dinheiro", default=0,
        help_text="Vendas com alguma parcela em espécie, entre as de forma conhecida.",
    )
    payments_known = models.PositiveIntegerField(
        "vendas com forma conhecida", default=0,
        help_text="Denominador da fatia de dinheiro. Zero conhecido é ausência, não zero.",
    )
    historical_dropped = models.PositiveIntegerField(
        "histórico descartado", default=0,
        help_text="Vendas históricas que ficaram de fora porque o dia teve pedido nativo (o dia nativo vence).",
    )
    refreshed_at = models.DateTimeField("atualizado em", auto_now=True)

    class Meta:
        verbose_name = "venda do dia (materializada)"
        verbose_name_plural = "vendas por dia (materializadas)"
        ordering = ["-date"]

    def __str__(self):
        return f"{self.date:%Y-%m-%d} · {self.orders} vendas · {self.source or 'sem venda'}"
