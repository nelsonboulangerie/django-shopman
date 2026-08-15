"""Episódios que atrapalharam o dia — detectados pelo sistema, explicados por gente.

A regra que governa este model: **o registro é automático; o humano só explica**.
Ninguém vai lembrar de anotar que faltou luz das 14h às 16h, e um formulário em
branco todo dia vira campo morto. Então o sistema observa o que ele já sabe
observar (a loja parou de vender no meio do expediente, a fornada planejada não
saiu) e, no fechamento, pergunta uma coisa só: *o que houve?* — com opções.

Daí a separação entre **sinal** e **motivo**:

- o **sinal** é o que o sistema mediu, e ele nasce sozinho (``detected_signal``);
- o **motivo** é o que só quem estava lá sabe (``kind``), e fica vazio até
  alguém dizer.

Episódio detectado e nunca explicado **continua valendo**: o dia foi atípico de
todo jeito, e isso já é motivo para não deixá-lo ensinar demanda. O que não
existe é o contrário — inventar o motivo a partir do sinal.

Forma: **episódio**, não atributo do dia. Tem começo, tem fim, e podem acontecer
vários no mesmo dia — é por isso que não é coluna em ``DayContext`` (lá moram os
valores únicos do dia: quanto tempo abriu, que temperatura fez).
"""

from __future__ import annotations

from django.db import models
from django.utils import timezone


class EpisodeStatus(models.TextChoices):
    SUSPECTED = "suspected", "A confirmar"      # o sistema notou, ninguém explicou
    CONFIRMED = "confirmed", "Confirmado"       # alguém disse o que houve
    DISMISSED = "dismissed", "Descartado"       # falso alarme, declarado


class OperationEpisodeKind(models.Model):
    """Catálogo do que pode ter acontecido — editável, sem código novo.

    Mesma ideia dos defeitos de qualidade: a casa cadastra o vocabulário que
    usa. ``affects_demand`` é o que dá consequência ao registro: um dia sem
    energia não pode ensinar que a procura é baixa.
    """

    ref = models.SlugField("ref", max_length=32, unique=True)
    label = models.CharField("rótulo", max_length=80)
    hint = models.CharField(
        "dica", max_length=140, blank=True,
        help_text="Segunda linha do botão, para o operador escolher sem pensar.",
    )
    affects_demand = models.BooleanField(
        "atrapalhou a venda", default=True,
        help_text="Se sim, o dia sai da amostra que ensina quanto produzir — "
                  "um dia atípico não deve virar previsão.",
    )
    position = models.PositiveSmallIntegerField("ordem", default=0)
    is_active = models.BooleanField("ativo", default=True)

    class Meta:
        verbose_name = "tipo de episódio"
        verbose_name_plural = "tipos de episódio"
        ordering = ["position", "label"]

    def __str__(self) -> str:
        return self.label


class OperationEpisode(models.Model):
    started_at = models.DateTimeField("começou em", db_index=True)
    ended_at = models.DateTimeField("terminou em", null=True, blank=True)
    status = models.CharField(
        "situação", max_length=16, choices=EpisodeStatus.choices,
        default=EpisodeStatus.SUSPECTED, db_index=True,
    )
    kind = models.ForeignKey(
        OperationEpisodeKind, verbose_name="o que houve", on_delete=models.PROTECT,
        null=True, blank=True, related_name="episodes",
        help_text="Vazio enquanto ninguém explicou. O sistema nunca preenche.",
    )
    detected_signal = models.CharField(
        "sinal detectado", max_length=200, blank=True,
        help_text="O que o sistema mediu, em português, para a pergunta fazer "
                  "sentido: 'nenhuma venda entre 14h e 16h'.",
    )
    detector = models.CharField(
        "quem detectou", max_length=32, blank=True, db_index=True,
        help_text="Quem levantou a lebre — usado para não duplicar o mesmo sinal.",
    )
    note = models.CharField("observação", max_length=200, blank=True)
    resolved_by = models.CharField("respondido por", max_length=100, blank=True)
    resolved_at = models.DateTimeField("respondido em", null=True, blank=True)
    created_at = models.DateTimeField("registrado em", auto_now_add=True)

    class Meta:
        verbose_name = "episódio de operação"
        verbose_name_plural = "episódios de operação"
        ordering = ["-started_at"]
        indexes = [
            models.Index(fields=["status", "started_at"], name="backstage_episode_status"),
        ]
        constraints = [
            # Um detector não repete o mesmo sinal no mesmo instante: rodar a
            # detecção duas vezes no dia não enche a tela de perguntas iguais.
            models.UniqueConstraint(
                fields=["detector", "started_at"],
                condition=models.Q(detector__gt=""),
                name="backstage_episode_one_per_detection",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.kind or self.detected_signal} ({self.started_at:%d/%m %H:%M})"

    @property
    def day(self):
        return timezone.localtime(self.started_at).date()

    @property
    def needs_answer(self) -> bool:
        return self.status == EpisodeStatus.SUSPECTED

    @property
    def affects_demand(self) -> bool:
        """Dia atípico não ensina demanda.

        Sem motivo declarado, o episódio ainda conta: o sinal existiu, e é mais
        seguro não aprender com um dia estranho do que aprender errado.
        """
        if self.status == EpisodeStatus.DISMISSED:
            return False
        return self.kind.affects_demand if self.kind else True
