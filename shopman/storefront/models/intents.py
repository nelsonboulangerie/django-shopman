"""Gabarito de intenções das mensagens de clientes — piloto (INTENT-PILOT-PLAN).

Duas tabelas, e nenhuma cópia de texto de cliente:

- ``IntentCategory``: o vocabulário de intenções da casa. É DADO, editável no
  Admin: a lista inicial vem do ``setup_intent_categories`` e o dono muda o que
  quiser sem código. ``sensitive`` marca as que não podem passar batido
  (reclamação, alergia, pedir uma pessoa): o placar mede essas à parte.
- ``MessageIntentSample``: uma mensagem do cliente sorteada para o gabarito e as
  intenções que uma pessoa marcou nela — **várias**, porque uma fala pode pedir,
  perguntar e reclamar ao mesmo tempo. Aponta para a ``ConversationMessage``
  (CASCADE): apagar a mensagem, por retenção ou por pedido do titular, apaga a
  amostra junto. O texto que a pessoa vê e que os classificadores recebem é
  sempre a versão **redigida** (``redact_observation_text``), calculada na hora.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone


class IntentCategory(models.Model):
    ref = models.SlugField("referência", max_length=40, unique=True)
    name = models.CharField("nome", max_length=80)
    description = models.CharField(
        "descrição", max_length=240,
        help_text="O que conta como esta intenção. Os classificadores leem esta frase.",
    )
    sensitive = models.BooleanField(
        "sensível", default=False,
        help_text="Deixar passar custa caro (reclamação, alergia, pedir uma pessoa). O placar mede à parte.",
    )
    position = models.PositiveSmallIntegerField("posição", default=0)
    active = models.BooleanField("ativa", default=True)

    class Meta:
        verbose_name = "intenção"
        verbose_name_plural = "intenções"
        ordering = ["position", "id"]

    def __str__(self) -> str:
        return self.name


class SampleStatus(models.TextChoices):
    PENDING = "pending", "a rotular"
    LABELED = "labeled", "rotulada"
    SKIPPED = "skipped", "pulada"


class MessageIntentSample(models.Model):
    message = models.OneToOneField(
        "shop.ConversationMessage",
        on_delete=models.CASCADE,
        related_name="intent_sample",
        verbose_name="mensagem",
    )
    intents = models.ManyToManyField(
        IntentCategory, blank=True, related_name="samples", verbose_name="intenções",
        help_text="Todas as que a mensagem carrega. Nenhuma marcada + rotulada = conversa sem intenção da lista.",
    )
    status = models.CharField(
        "estado", max_length=10, choices=SampleStatus.choices, default=SampleStatus.PENDING, db_index=True,
    )
    note = models.CharField("observação", max_length=200, blank=True)
    labeled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="rotulada por",
    )
    labeled_at = models.DateTimeField("rotulada em", null=True, blank=True)
    created_at = models.DateTimeField("sorteada em", auto_now_add=True)

    class Meta:
        verbose_name = "mensagem para rotular"
        verbose_name_plural = "mensagens para rotular"
        ordering = ["status", "id"]

    def __str__(self) -> str:
        return f"Mensagem {self.message_id}"

    def mark_labeled(self, user) -> None:
        """A assinatura do gabarito: quem e quando. Não salva."""
        self.status = SampleStatus.LABELED
        self.labeled_by = user
        self.labeled_at = timezone.now()

    def redacted_text(self) -> str:
        from shopman.storefront.concierge.observation_privacy import redact_observation_text

        return redact_observation_text(self.message.text or "").text
