"""O medidor das APIs pagas que não são IA: uma linha por chamada (DEV-2026-067).

Mesmo desenho do medidor da IA (``AiInvocation``): toda chamada que custa dinheiro
deixa rastro, inclusive a recusada pelo teto, para a loja saber quanto usa e quanto
gasta (o B.I. de uso soma por dia, provedor e função). O primeiro consumidor é a
manobra da tela "Dirigindo" do entregador da casa, pelo Routes API do Google (#2509).

Dinheiro é inteiro (C2): o preço do provedor é em dólar, então vai em micro-dólares
(``_usd_micros``). Nenhum campo guarda o que foi enviado ao provedor (a coordenada do
entregador é dado pessoal).
"""

from __future__ import annotations

from django.db import models
from shopman.utils.formatting import format_local


class PaidApiOutcome(models.TextChoices):
    OK = "ok", "ok"
    ERROR = "error", "erro"
    DENIED = "denied", "teto do dia atingido"


class PaidApiCall(models.Model):
    provider = models.CharField("provedor", max_length=40, db_index=True)
    purpose = models.CharField("função", max_length=40)
    outcome = models.CharField("resultado", max_length=20, choices=PaidApiOutcome.choices)
    error_type = models.CharField("tipo do erro", max_length=80, blank=True)
    #: O preço de tabela do provedor na hora da chamada (zero na recusada e no erro de rede).
    cost_usd_micros = models.PositiveBigIntegerField("custo estimado (micro-US$)", default=0)
    latency_ms = models.PositiveIntegerField("latência (ms)", default=0)
    created_at = models.DateTimeField("quando", auto_now_add=True, db_index=True)

    class Meta:
        app_label = "shop"
        verbose_name = "chamada de API paga"
        verbose_name_plural = "chamadas de API paga"
        ordering = ("-created_at",)
        indexes = [models.Index(fields=["provider", "created_at"], name="shop_paidapi_provider_created")]

    def __str__(self) -> str:
        return f"{self.provider} {self.purpose} {self.outcome} {format_local(self.created_at, '%d/%m {clock}')}"

    @property
    def cost_usd(self) -> float:
        return self.cost_usd_micros / 1_000_000
