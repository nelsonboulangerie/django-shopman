"""Contexto do dia — o que estava acontecendo além da loja.

Uma linha por data, com dois blocos INDEPENDENTES e ambos OPCIONAIS:

- **feriado** (`holiday_name`/`holiday_scope`, e véspera/volta derivadas): vem
  de um calendário anual injetado uma vez por ano.
- **clima** (temperatura e chuva): vem de um arquivo de dados meteorológicos.

A regra que governa os dois: **sem dado, nenhuma afirmação**. Um dia sem clima
carregado não é um dia de temperatura zero — é um dia sobre o qual não sabemos
nada, e ele fica fora de qualquer leitura por temperatura. O mesmo vale para
feriado. É por isso que os campos são nulos em vez de terem default: nulo é
"não sei", e "não sei" nunca vira número numa média.

O que a suite deriva sozinha do calendário (dia da semana, mês, semana do ano)
NÃO mora aqui — é função da data e sai calculado na leitura. Aqui fica só o que
a suite não tem como saber sem alguém contar.

Não é ledger nem fonte de fato de negócio: é contexto externo materializado,
recarregável a qualquer momento (ADR-021 §3, mesma natureza do histórico
externo). Recarregar corrige; nunca duplica.
"""

from __future__ import annotations

from django.db import models


class HolidayScope(models.TextChoices):
    NATIONAL = "national", "Nacional"
    STATE = "state", "Estadual"
    CITY = "city", "Municipal"


class DayContext(models.Model):
    date = models.DateField("data", unique=True)

    # ── Feriado (injetado; vazio = dia comum declarado, nulo = sem calendário)
    holiday_name = models.CharField("feriado", max_length=120, blank=True)
    holiday_scope = models.CharField(
        "abrangência", max_length=16, choices=HolidayScope.choices, blank=True
    )
    is_holiday_eve = models.BooleanField(
        "véspera de feriado", default=False,
        help_text="Derivado na carga do calendário: o dia anterior a um feriado.",
    )
    is_post_holiday = models.BooleanField(
        "volta de feriado", default=False,
        help_text="Derivado na carga do calendário: o dia seguinte a um feriado.",
    )
    has_calendar = models.BooleanField(
        "calendário carregado", default=False,
        help_text="Se falso, esta data não foi coberta por nenhum calendário — "
                  "não afirmamos que é dia comum, apenas não sabemos.",
    )

    # ── Clima (injetado; nulo = sem dado, nunca zero)
    temp_min_c = models.DecimalField(
        "temperatura mínima (°C)", max_digits=4, decimal_places=1, null=True, blank=True
    )
    temp_max_c = models.DecimalField(
        "temperatura máxima (°C)", max_digits=4, decimal_places=1, null=True, blank=True
    )
    temp_avg_c = models.DecimalField(
        "temperatura média (°C)", max_digits=4, decimal_places=1, null=True, blank=True
    )
    rain_mm = models.DecimalField(
        "chuva (mm)", max_digits=6, decimal_places=1, null=True, blank=True
    )

    sources = models.JSONField(
        "origens", default=dict, blank=True,
        help_text="De onde veio cada bloco, ex.: "
                  '{"holiday": "calendario-2026.json", "weather": "inmet-londrina.csv"}.',
    )
    updated_at = models.DateTimeField("atualizado em", auto_now=True)

    class Meta:
        verbose_name = "contexto do dia"
        verbose_name_plural = "contextos do dia"
        ordering = ["-date"]
        indexes = [
            models.Index(fields=["date"], name="backstage_daycontext_date"),
        ]

    def __str__(self) -> str:
        return f"{self.date} {self.holiday_name or ''}".strip()

    @property
    def has_weather(self) -> bool:
        """Só afirma clima quando há pelo menos a máxima do dia."""
        return self.temp_max_c is not None

    @property
    def is_holiday(self) -> bool:
        return bool(self.holiday_name)

    @property
    def day_kind(self) -> str:
        """Feriado, véspera, volta ou dia comum — só com calendário carregado."""
        if not self.has_calendar:
            return ""
        if self.is_holiday:
            return "holiday"
        if self.is_holiday_eve:
            return "holiday_eve"
        if self.is_post_holiday:
            return "post_holiday"
        return "regular"
