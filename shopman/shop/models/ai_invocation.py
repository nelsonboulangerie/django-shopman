"""O medidor da porta de IA: uma linha por chamada, e o contador do dia.

Até 11/11/2026 nenhuma chamada a modelo deixava rastro na casa, e um placar em
loop gastou cerca de US$ 1.180 em duas semanas sem ninguém ver (ID3A-PLAN, E1).
Agora toda chamada que passa pela porta (``shopman.shop.ai``) grava um
``AiInvocation``, inclusive a recusada pelo freio, e soma no ``AiSpendDay``, que
é ao mesmo tempo o teto do orçamento e o agregado diário.

Dinheiro é inteiro (C2). O custo da API é em dólar, então vai em micro-dólares
(``_usd_micros``): o sufixo ``_q`` é centavo de real e misturar as duas moedas no
mesmo sufixo mentiria. Nenhum campo guarda o texto enviado ao provedor.
"""

from __future__ import annotations

from django.db import models


class AiOutcome(models.TextChoices):
    OK = "ok", "ok"
    ERROR = "error", "erro"
    KILLED = "killed", "IA desligada na loja"
    BUDGET_DENIED = "budget_denied", "teto de gasto atingido"


class AiInvocation(models.Model):
    purpose = models.CharField("função", max_length=40, db_index=True)
    connection_ref = models.CharField("conexão", max_length=40, blank=True)
    model = models.CharField("modelo", max_length=80, blank=True)
    outcome = models.CharField("resultado", max_length=20, choices=AiOutcome.choices)
    error_type = models.CharField("tipo do erro", max_length=80, blank=True)
    tokens_in = models.PositiveIntegerField("tokens de entrada", default=0)
    tokens_out = models.PositiveIntegerField("tokens de saída", default=0)
    tokens_cache_read = models.PositiveIntegerField("tokens lidos do cache", default=0)
    tokens_cache_write = models.PositiveIntegerField("tokens escritos no cache", default=0)
    reserved_usd_micros = models.PositiveBigIntegerField("reserva (micro-US$)", default=0)
    cost_usd_micros = models.PositiveBigIntegerField("custo (micro-US$)", default=0)
    #: O modelo não está na tabela pública de preço: o custo foi contado pelo preço
    #: mais alto da tabela, para o teto errar do lado seguro.
    cost_estimated = models.BooleanField("custo estimado", default=False)
    latency_ms = models.PositiveIntegerField("latência (ms)", default=0)
    created_at = models.DateTimeField("quando", auto_now_add=True, db_index=True)

    class Meta:
        app_label = "shop"
        verbose_name = "chamada de IA"
        verbose_name_plural = "chamadas de IA"
        ordering = ("-created_at",)
        indexes = [models.Index(fields=["purpose", "created_at"], name="shop_aiinv_purpose_created")]

    def __str__(self) -> str:
        return f"{self.purpose} {self.outcome} {self.created_at:%d/%m %H:%M}"

    @property
    def cost_usd(self) -> float:
        return self.cost_usd_micros / 1_000_000


class AiSpendDay(models.Model):
    """Gasto de um dia num escopo: ``shop`` (a loja inteira) ou o nome da função."""

    date = models.DateField("dia")
    scope = models.CharField("escopo", max_length=40)
    calls = models.PositiveIntegerField("chamadas", default=0)
    errors = models.PositiveIntegerField("erros", default=0)
    denied = models.PositiveIntegerField("recusadas pelo freio", default=0)
    reserved_usd_micros = models.BigIntegerField("reservado (micro-US$)", default=0)
    spent_usd_micros = models.PositiveBigIntegerField("gasto (micro-US$)", default=0)

    class Meta:
        app_label = "shop"
        verbose_name = "gasto de IA do dia"
        verbose_name_plural = "gasto de IA por dia"
        ordering = ("-date", "scope")
        constraints = [models.UniqueConstraint(fields=["date", "scope"], name="shop_aispendday_unique")]

    def __str__(self) -> str:
        return f"{self.date:%d/%m/%Y} {self.scope}: US$ {self.spent_usd:.4f}"

    @property
    def spent_usd(self) -> float:
        return self.spent_usd_micros / 1_000_000
