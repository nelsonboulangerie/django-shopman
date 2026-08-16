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

    # ── Data comercial (injetada) — dia das mães, Páscoa, dia dos namorados…
    # Fica separada do feriado porque a consequência é outra: feriado pode
    # FECHAR a loja, data comercial nunca fecha — ela enche. Guardar as duas no
    # mesmo campo obrigaria a escolher entre perder o Natal como feriado ou
    # perdê-lo como data comercial, e ele é os dois.
    commercial_name = models.CharField(
        "data comercial", max_length=120, blank=True,
        help_text="Data que move o movimento sem ser feriado (ou além de ser).",
    )

    # Derivados da UNIÃO das duas: a véspera do dia das mães enche uma padaria
    # tanto quanto a véspera de um feriado.
    is_special_eve = models.BooleanField(
        "véspera de data especial", default=False,
        help_text="Derivado na carga: o dia anterior a um feriado ou data comercial.",
    )
    is_post_special = models.BooleanField(
        "volta de data especial", default=False,
        help_text="Derivado na carga: o dia seguinte a um feriado ou data comercial.",
    )
    # De QUAL data este dia é véspera. Guardar o nome, e não só o booleano, tem
    # motivo declarado pelo dono: numa padaria fechada no dia seguinte, **é na
    # véspera que o dinheiro acontece** — então ela é ocasião por direito
    # próprio, e a véspera do dia das mães não é a véspera de um feriado
    # qualquer. A volta segue sendo só um booleano de propósito: nela o
    # movimento apenas esvazia, e o motivo não muda a decisão.
    eve_of = models.CharField(
        "véspera de", max_length=120, blank=True,
        help_text="Nome da data especial do dia seguinte. Derivado na carga.",
    )
    has_calendar = models.BooleanField(
        "calendário carregado", default=False,
        help_text="Se falso, esta data não foi coberta por nenhum calendário — "
                  "não afirmamos que é dia comum, apenas não sabemos.",
    )

    # ── Operação do dia (carimbada; é o DENOMINADOR das métricas de tempo)
    open_minutes = models.PositiveIntegerField(
        "minutos de expediente", null=True, blank=True,
        help_text="Quanto tempo a casa esteve aberta NESTE dia, congelado. "
                  "0 = não abriu. Nulo = não sabemos (dia anterior à medição).",
    )
    opens_at = models.TimeField("abriu às", null=True, blank=True)
    closes_at = models.TimeField("fechou às", null=True, blank=True)
    closed_reason = models.CharField(
        "motivo do fechamento", max_length=120, blank=True,
        help_text="Por que não abriu: feriado, férias coletivas, dia sem "
                  "expediente regular. Vazio quando abriu.",
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
    def was_open(self) -> bool:
        return bool(self.open_minutes)

    @property
    def is_holiday(self) -> bool:
        return bool(self.holiday_name)

    @property
    def day_kind(self) -> str:
        """Que tipo de dia é este — só com calendário carregado.

        **A data comercial tem identidade própria**, e não um balde genérico:
        perguntar "o que esperar no dia das mães" tem de comparar com dias das
        mães, não com o dia dos namorados. Jogar todas num balde "data
        comercial" responderia a pergunta errada com aparência de certeza.

        A ordem também é intencional: o dia em si vence o derivado (véspera,
        volta), e a data comercial vence o feriado porque é mais específica —
        o Natal é os dois, e "Natal" diz mais do que "feriado". Se a loja fecha
        nesse dia, quem cuida disso é o expediente carimbado, não este rótulo.
        """
        if not self.has_calendar:
            return ""
        if self.commercial_name:
            return f"commercial:{self.commercial_name.strip().lower()}"
        if self.is_holiday:
            return "holiday"
        if self.eve_of:
            return f"eve:{self.eve_of.strip().lower()}"
        if self.is_special_eve:
            return "special_eve"
        if self.is_post_special:
            return "post_special"
        return "regular"

    @property
    def day_kind_label(self) -> str:
        """O rótulo legível do tipo de dia. Vazio quando não sabemos."""
        if self.commercial_name:
            return self.commercial_name
        if self.eve_of and not self.is_holiday:
            return f"{self.eve_of} (véspera)"
        return {
            "holiday": "Feriado",
            "special_eve": "Véspera de data especial",
            "post_special": "Volta de data especial",
            "regular": "Dia comum",
        }.get(self.day_kind, "")

    @property
    def occasion_name(self) -> str:
        """A data especial de que este dia participa, se houver.

        A véspera devolve o nome da data que ela antecede, porque é a mesma
        ocasião vista do dia em que a padaria de fato vende.
        """
        return self.commercial_name or self.eve_of

    @property
    def occasion_is_eve(self) -> bool:
        return not self.commercial_name and bool(self.eve_of)
