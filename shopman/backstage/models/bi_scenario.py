"""Cenários com IA — o B.I. propõe, versionado; nunca executa (BI-DATA-FOUNDATION-PLAN §7.1).

Um ``BIScenarioReport`` é o registro de UMA rodada: o que a IA viu (os
agregados da camada de leitura, serializados, com o hash — para reproduzir "o
que ela viu"), o que ela devolveu (cru e interpretado), quem pediu, com que
modelo, em quanto tempo. Append-only: a leitura de um dia é a leitura daquele
dia, e relatório que muda depois de lido é relatório em que ninguém confia.

Três limites, escritos para não serem esquecidos:
- **Só camada de leitura.** Nenhum ``Order``, nenhuma ``HistoricalSale``,
  nenhum nome de cliente entra no prompt — entram as projections já agregadas,
  com unidade.
- **Propositivo.** A IA sugere cenários; não cria fornada, não muda regra, não
  toca em nada. Quem decide é o gestor, na tela de plano.
- **Falha é ausência declarada.** Provedor fora, resposta fora do contrato,
  credencial ausente: o relatório nasce ``failed`` com o motivo, nunca com um
  cenário inventado.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models


class BIScenarioReport(models.Model):
    class Focus(models.TextChoices):
        SALES = "sales", "Vendas"
        PRODUCTION = "production", "Produção"

    class Status(models.TextChoices):
        DONE = "done", "concluído"
        FAILED = "failed", "falhou"

    generated_at = models.DateTimeField("gerado em", auto_now_add=True, db_index=True)
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="+", verbose_name="pedido por",
    )
    focus = models.CharField("foco", max_length=16, choices=Focus.choices)
    window_from = models.DateField("janela de")
    window_to = models.DateField("janela até")
    model = models.CharField("modelo", max_length=64, blank=True)
    status = models.CharField("estado", max_length=8, choices=Status.choices, default=Status.DONE)
    duration_ms = models.PositiveIntegerField("duração (ms)", default=0)
    inputs_hash = models.CharField(
        "hash das entradas", max_length=64, blank=True,
        help_text="sha256 dos agregados enviados: duas rodadas com o mesmo hash viram a mesma pergunta.",
    )
    inputs = models.JSONField(
        "entradas", default=dict, blank=True,
        help_text="Os agregados que a IA viu — só camada de leitura, com unidade. Nunca dado pessoal.",
    )
    scenarios = models.JSONField(
        "cenários", default=list, blank=True,
        help_text="[{title, basis[], proposal, unknowns[]}] como a IA devolveu, validado.",
    )
    raw_text = models.TextField("resposta crua", blank=True)
    error = models.TextField("erro", blank=True)

    class Meta:
        verbose_name = "cenários gerados pela IA"
        verbose_name_plural = "cenários gerados pela IA"
        ordering = ["-generated_at"]

    def __str__(self):
        return f"{self.get_focus_display()} · {self.generated_at:%d/%m %H:%M} · {self.get_status_display()}"
