"""O corpus anonimizado de aprendizado conversacional (dono, 20/11/2026, #2851).

Uma cópia das mensagens observadas que **não liga mais à pessoa**, para medir e
treinar a Concierge sem o prazo de 1 a 30 dias da observação (LGPD, art. 12: dado
anonimizado não é dado pessoal). Por isso, de propósito, aqui NÃO há:

- conversa, vínculo de transporte, subject, ``external_id`` nem a mensagem de origem
  (nenhuma chave estrangeira para o que é da pessoa, e nenhuma tabela de
  correspondência: nunca se reidentifica);
- hora exata nem data: fica o dia da semana e a faixa de três horas.

O texto é o já redigido na captura (``observation_privacy``) mais uma segunda passada
(``concierge.corpus.anonymize``). Uma amostra por semana vai à conferência de um curador
(``shop.review_conversation_observations``); dado pessoal achado nela pausa a cópia.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models


class CorpusReview(models.TextChoices):
    #: Fora da amostra da semana: ninguém precisa conferir.
    NOT_SAMPLED = "not_sampled", "Fora da amostra"
    PENDING = "pending", "Na amostra, a conferir"
    CLEAN = "clean", "Conferida: sem dado pessoal"
    #: Achado de dado pessoal: a cópia pausa até o curador tratar (apagar a linha).
    PERSONAL_DATA = "personal_data", "Achou dado pessoal"


class CorpusOutcome(models.TextChoices):
    OBSERVED = "observed", "Só observada (a Concierge não respondia)"
    UNDERSTOOD = "understood", "Entendeu"
    VERIFYING = "verifying", "Vou verificar"
    TEAM = "team", "Foi para a equipe"
    ORDER = "order", "Virou pedido"


class ConversationCorpusEntry(models.Model):
    text = models.TextField("texto anonimizado")
    #: As limpezas aplicadas (as categorias da captura e as da segunda passada).
    redactions = models.JSONField("limpezas", default=list, blank=True)
    #: A intenção lida (a da triagem em sombra, quando houve); vazio quando ninguém leu.
    intent = models.CharField("intenção lida", max_length=40, blank=True)
    outcome = models.CharField("resultado", max_length=20, choices=CorpusOutcome.choices)
    channel = models.CharField("canal", max_length=20, blank=True)
    #: 0 = segunda-feira (``date.weekday``).
    weekday = models.PositiveSmallIntegerField("dia da semana")
    #: Início da faixa de três horas, no fuso da loja: 0, 3, 6, ..., 21.
    hour_band = models.PositiveSmallIntegerField("faixa de horário")
    #: Semana ISO da cópia (``2026-W47``): só para sortear a amostra da semana. Não diz o
    #: dia nem a hora da mensagem.
    sample_week = models.CharField("semana da amostra", max_length=10, blank=True, db_index=True)
    review = models.CharField(
        "conferência", max_length=20, choices=CorpusReview.choices, default=CorpusReview.NOT_SAMPLED, db_index=True
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
        verbose_name="conferida por",
    )
    review_note = models.CharField("observação da conferência", max_length=200, blank=True)

    class Meta:
        verbose_name = "mensagem do corpus anonimizado"
        verbose_name_plural = "corpus anonimizado de conversas"
        ordering = ["-id"]

    def __str__(self) -> str:
        return f"Corpus {self.pk}"
