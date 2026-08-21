"""Alarmes do B.I. — regras configuráveis no Admin, avaliadas contra a camada de leitura.

O B.I. deixa de ser só "o que aconteceu" para avisar quando o que aconteceu
foge do esperado (BI-DATA-FOUNDATION-PLAN §7.2). Duas peças:

- ``BIAlertRule``: a regra, como dado. Que métrica, com que régua, com que
  severidade, e — obrigatório — com que **cooldown**: um alarme que grita a
  cada ciclo de cinco minutos ensina a casa a ignorá-lo, e o aviso legítimo
  morre junto. O gestor edita; a regra roda como configurada ou não roda.
- ``BIAlertEvent``: o disparo, append-only. Valor medido, baseline, mensagem,
  e o ``OperatorAlert`` que nasceu dele (o bus de alertas com reconhecimento
  que o operador já usa — canal único no v1, sem e-mail).

**Baseline sem modelo.** "Esperado" é a média do mesmo dia da semana nas
últimas N semanas, lida da série diária materializada, fora dos dias fechados
e atrapalhados (a mesma régua de "dia parecido" que a projeção usa). Sem
amostra suficiente a regra não opina — ausência declarada, nunca número.

**Cinco métricas**, cada uma com os seus parâmetros explícitos (colunas
claras valem mais que um ``threshold`` genérico com unidade):
- ``import_silence``: a origem ``source`` deveria receber lote a cada
  ``expected_every_days`` dias e não recebeu — o candidato forte da missão.
- ``daily_revenue_vs_baseline``: o faturamento de ontem ficou abaixo de
  ``threshold_percent`` % da média do mesmo dia da semana.
- ``native_overrides_history``: nos últimos ``lookback_days``, um dia com até
  ``max_native_orders`` pedidos nativos apagou mais de ``min_historical_dropped``
  vendas históricas (o guard da fusão, persistido em ``DailySalesFact``).
- ``cash_variance_by_drawer``: nos últimos ``lookback_days``, a quebra
  acumulada de alguma GAVETA passou de ``threshold_q`` centavos. Por gaveta
  porque a custódia é do terminal e várias pessoas trabalham no mesmo turno;
  o NOME entra só quando o livro prova que uma pessoa lançou sozinha. ⚠️ É
  **apuração**: o aviso ao operador não carrega nome nem valor; o detalhe
  fica no disparo, visível só para quem tem ``cashman.audit_shift``.
- ``curation_pending``: no último lote concluído de ``source``, mais de
  ``threshold_percent`` % das linhas não têm de-para de produto confirmado —
  há curadoria pendente antes de o número ser confiável.
"""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import models

from .alerts import OperatorAlert


class BIAlertRule(models.Model):
    class Metric(models.TextChoices):
        IMPORT_SILENCE = "import_silence", "Importação esperada não chegou"
        DAILY_REVENUE_VS_BASELINE = "daily_revenue_vs_baseline", "Faturamento do dia abaixo do esperado"
        NATIVE_OVERRIDES_HISTORY = "native_overrides_history", "Pedido nativo apagou histórico"
        CASH_VARIANCE_BY_DRAWER = "cash_variance_by_drawer", "Quebra de caixa acumulada por gaveta"
        CURATION_PENDING = "curation_pending", "De-para de produto pendente"

    #: Métricas que são apuração de caixa: o disparo detalhado só para quem audita.
    AUDIT_ONLY_METRICS = frozenset({"cash_variance_by_drawer"})

    ref = models.SlugField("ref", max_length=48, unique=True)
    label = models.CharField("rótulo", max_length=120)
    metric = models.CharField("métrica", max_length=32, choices=Metric.choices)
    is_active = models.BooleanField("ativo", default=True)
    severity = models.CharField(
        "severidade", max_length=10, choices=OperatorAlert.SEVERITY_CHOICES, default="warning",
    )
    cooldown_minutes = models.PositiveIntegerField(
        "silêncio após disparar (minutos)",
        help_text="Obrigatório. Depois de disparar, a regra não avisa de novo antes disto — "
        "alarme que grita a cada ciclo vira ruído e o aviso legítimo morre junto.",
    )
    # ── parâmetros de import_silence ──
    source = models.CharField(
        "origem esperada", max_length=16, blank=True,
        help_text="Só para 'importação esperada não chegou': a origem (ex.: yooga).",
    )
    expected_every_days = models.PositiveSmallIntegerField(
        "a cada quantos dias", null=True, blank=True,
        help_text="Só para 'importação esperada não chegou': a cadência esperada de lote concluído.",
    )
    # ── parâmetros de daily_revenue_vs_baseline ──
    threshold_percent = models.PositiveSmallIntegerField(
        "dispara abaixo de (% do esperado)", null=True, blank=True,
        help_text="Só para 'faturamento abaixo do esperado': ontem < X% da média do mesmo dia da semana.",
    )
    baseline_weeks = models.PositiveSmallIntegerField(
        "semanas de baseline", default=4,
        help_text="Quantas semanas para trás entram na média do mesmo dia da semana.",
    )
    # ── parâmetros de native_overrides_history / cash_variance_by_drawer / curation_pending ──
    lookback_days = models.PositiveSmallIntegerField(
        "olhar para trás (dias)", default=7,
        help_text="Janela das métricas acumuladas: histórico apagado, quebra de caixa.",
    )
    max_native_orders = models.PositiveSmallIntegerField(
        "até quantos pedidos nativos", null=True, blank=True,
        help_text="Só para 'pedido nativo apagou histórico': dia com ATÉ isto de pedidos nativos…",
    )
    min_historical_dropped = models.PositiveIntegerField(
        "…que apagou mais de quantas vendas históricas", null=True, blank=True,
    )
    threshold_q = models.BigIntegerField(
        "régua em centavos", null=True, blank=True,
        help_text="Só para 'quebra de caixa acumulada': |Σ quebra| de um operador na janela acima disto dispara.",
    )
    # ── o que a última avaliação viu (para o Admin mostrar; o disparo fica no evento) ──
    last_evaluated_at = models.DateTimeField("avaliado em", null=True, blank=True)
    last_fired_at = models.DateTimeField("disparou em", null=True, blank=True)
    last_reading = models.JSONField(
        "última leitura", default=dict, blank=True,
        help_text="{value, baseline, fired, message} da última avaliação. Ausência de valor = a regra não opinou.",
    )

    class Meta:
        verbose_name = "alarme do B.I."
        verbose_name_plural = "alarmes do B.I."
        ordering = ["label"]

    def __str__(self):
        return self.label

    def clean(self):
        if self.cooldown_minutes is not None and self.cooldown_minutes < 1:
            raise ValidationError({"cooldown_minutes": "O silêncio após disparar precisa ser de pelo menos 1 minuto."})
        if self.metric == self.Metric.IMPORT_SILENCE:
            if not self.source:
                raise ValidationError({"source": "Diga qual origem deveria receber lote."})
            if not self.expected_every_days:
                raise ValidationError({"expected_every_days": "Diga a cada quantos dias o lote é esperado."})
        if self.metric == self.Metric.DAILY_REVENUE_VS_BASELINE:
            if not self.threshold_percent or self.threshold_percent >= 100:
                raise ValidationError({"threshold_percent": "Informe um percentual do esperado entre 1 e 99."})
            if not self.baseline_weeks:
                raise ValidationError({"baseline_weeks": "Pelo menos uma semana de baseline."})
        if self.metric == self.Metric.NATIVE_OVERRIDES_HISTORY:
            if self.max_native_orders is None or not self.min_historical_dropped:
                raise ValidationError("Diga até quantos pedidos nativos e acima de quantas vendas históricas apagadas.")
        if self.metric == self.Metric.CASH_VARIANCE_BY_DRAWER and not self.threshold_q:
            raise ValidationError({"threshold_q": "Diga a régua da quebra acumulada, em centavos."})
        if self.metric == self.Metric.CURATION_PENDING:
            if not self.source:
                raise ValidationError({"source": "Diga de qual origem conferir o de-para."})
            if not self.threshold_percent or self.threshold_percent >= 100:
                raise ValidationError({"threshold_percent": "Informe um percentual de linhas sem de-para entre 1 e 99."})
        if self.metric in (
            self.Metric.NATIVE_OVERRIDES_HISTORY, self.Metric.CASH_VARIANCE_BY_DRAWER,
        ) and not self.lookback_days:
            raise ValidationError({"lookback_days": "Pelo menos um dia de janela."})


class BIAlertEvent(models.Model):
    """Um disparo. Append-only: o que o alarme viu, quando, e o aviso que gerou."""

    rule = models.ForeignKey(BIAlertRule, on_delete=models.PROTECT, related_name="events", verbose_name="alarme")
    fired_at = models.DateTimeField("disparou em", auto_now_add=True, db_index=True)
    severity = models.CharField("severidade", max_length=10, choices=OperatorAlert.SEVERITY_CHOICES)
    value = models.FloatField("valor medido", null=True, blank=True)
    baseline = models.FloatField("esperado", null=True, blank=True)
    message = models.TextField("mensagem")
    operator_alert = models.ForeignKey(
        OperatorAlert, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="bi_alert_events", verbose_name="aviso ao operador",
    )

    class Meta:
        verbose_name = "disparo de alarme do B.I."
        verbose_name_plural = "disparos de alarme do B.I."
        ordering = ["-fired_at"]

    def __str__(self):
        return f"{self.rule.label} · {self.fired_at:%d/%m %H:%M}"
