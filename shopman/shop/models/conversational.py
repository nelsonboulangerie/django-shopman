"""O registro do framework de comércio conversacional no Shopman: decisão e resultado (N5).

Só acréscimo. A decisão em sombra (``storefront/concierge/shadow.py``) grava aqui o que o
framework faria com cada entrada, sem enviar nada nem escrever no comércio; a junção grava
depois o resultado observado (pedidos do cliente em 24 h e em 7 dias).

- **Nenhum texto do cliente**: o registro guarda a referência da mensagem, os atos, os
  movimentos, os códigos de bloqueio e os hashes do ``DecisionRecord`` e do snapshot.
- **Uma entrada, um registro** (K01): a mensagem é única aqui; varrer duas vezes não duplica.
- **O que deriva da observação some com ela**: a mensagem apagada pela retenção
  (``service.purge_observations``) leva a decisão e os resultados junto (``CASCADE``).
- **Resultado imaturo é censura, não zero** (K33): janela aberta grava ``censored`` sem
  valor; a observação madura é um registro novo que ``supersedes`` o anterior (K35).
"""

from __future__ import annotations

from django.db import models


class ConversationalDecision(models.Model):
    """O ``DecisionRecord`` do framework para uma entrada, em sombra."""

    message = models.OneToOneField(
        "shop.ConversationMessage", on_delete=models.CASCADE, related_name="conversational_decision",
        verbose_name="entrada",
    )
    conversation_id = models.PositiveBigIntegerField("conversa", db_index=True)
    environment = models.CharField("ambiente", max_length=16, default="shadow")
    decision_id = models.CharField("decisão", max_length=128, unique=True)
    decision_hash = models.CharField("hash da decisão", max_length=80)
    snapshot_hash = models.CharField("hash do snapshot", max_length=80)
    profile_version = models.CharField("versão do perfil", max_length=32)
    acts = models.JSONField("atos", default=list, blank=True)
    chosen_moves = models.JSONField("movimentos escolhidos", default=list, blank=True)
    blocked = models.JSONField("bloqueios por movimento", default=dict, blank=True)
    unknown_facts = models.JSONField("fatos desconhecidos e a fonte", default=dict, blank=True)
    # O documento inteiro do framework (``DecisionRecord.to_document()``): explica cada proposta.
    document = models.JSONField("documento da decisão", default=dict)
    customer_ref = models.CharField("ref do cliente", max_length=64, blank=True, db_index=True)
    entry_at = models.DateTimeField("entrada em")
    decided_at = models.DateTimeField("decidida em", db_index=True)

    class Meta:
        app_label = "shop"
        verbose_name = "decisão em sombra"
        verbose_name_plural = "decisões em sombra"
        ordering = ("-decided_at",)

    def __str__(self) -> str:
        return f"{self.decision_id} ({', '.join(self.chosen_moves) or 'nenhum movimento'})"


class ConversationalOutcome(models.Model):
    """Um ``OutcomeEvent``: pedidos do cliente na janela depois da decisão. Só acréscimo."""

    class Observation(models.TextChoices):
        OBSERVED = "observed", "observado"
        CENSORED = "censored", "censurado (janela aberta)"
        UNKNOWN = "unknown", "desconhecido"
        NOT_APPLICABLE = "not_applicable", "não se aplica"

    decision = models.ForeignKey(ConversationalDecision, on_delete=models.CASCADE, related_name="outcomes",
                                 verbose_name="decisão")
    outcome_id = models.CharField("resultado", max_length=128, unique=True)
    metric = models.CharField("métrica", max_length=64)
    definition_version = models.CharField("versão da definição", max_length=16, default="1")
    window_start = models.DateTimeField("janela desde")
    window_end = models.DateTimeField("janela até")
    observation = models.CharField("observação", max_length=16, choices=Observation.choices)
    value = models.JSONField("valor", null=True, blank=True)
    source = models.CharField("fonte", max_length=64)
    supersedes = models.OneToOneField("self", on_delete=models.CASCADE, null=True, blank=True,
                                      related_name="superseded_by", verbose_name="substitui")
    recorded_at = models.DateTimeField("gravado em", auto_now_add=True)

    class Meta:
        app_label = "shop"
        verbose_name = "resultado da decisão em sombra"
        verbose_name_plural = "resultados das decisões em sombra"
        ordering = ("decision", "metric", "recorded_at")
        constraints = [
            models.CheckConstraint(
                condition=(models.Q(observation="observed", value__isnull=False)
                           | (~models.Q(observation="observed") & models.Q(value__isnull=True))),
                name="shop_convoutcome_value_iff_observed",
            ),
        ]


# ── Armazenamento do framework (N8): episódio, registros, trabalho ─────────────────


class ConversationalEpisode(models.Model):
    """O estado vigente de um episódio do framework. Uma linha por episódio, comparar e gravar."""

    tenant = models.CharField("inquilino", max_length=64)
    environment = models.CharField("ambiente", max_length=16)
    episode_id = models.CharField("episódio", max_length=128)
    subject = models.CharField("sujeito", max_length=256, blank=True, db_index=True)
    state = models.CharField("estado", max_length=32)
    version = models.PositiveIntegerField("versão")
    # O ``Episode`` do framework (``to_document()``): a forma é a do contrato, não daqui.
    document = models.JSONField("documento")
    occurred_at = models.DateTimeField("ocorrido em", db_index=True)

    class Meta:
        app_label = "shop"
        verbose_name = "episódio conversacional"
        verbose_name_plural = "episódios conversacionais"
        constraints = [
            models.UniqueConstraint(fields=["tenant", "environment", "episode_id"],
                                    name="shop_convepisode_unique_per_tenant"),
        ]


class ConversationalRecord(models.Model):
    """Um registro do framework gravado no episódio (evento, snapshot, decisão, resposta, recibo...).

    Só acréscimo. ``dedupe_key`` só existe para o evento com identidade estável: a mesma
    identidade grava uma vez (K01).
    """

    tenant = models.CharField("inquilino", max_length=64)
    environment = models.CharField("ambiente", max_length=16)
    episode_id = models.CharField("episódio", max_length=128, blank=True)
    schema = models.CharField("contrato", max_length=64)
    record_id = models.CharField("registro", max_length=128)
    dedupe_key = models.CharField("identidade do evento", max_length=512, null=True, blank=True)
    document = models.JSONField("documento")
    recorded_at = models.DateTimeField("gravado em", auto_now_add=True)

    class Meta:
        app_label = "shop"
        verbose_name = "registro conversacional"
        verbose_name_plural = "registros conversacionais"
        indexes = [models.Index(fields=["tenant", "environment", "episode_id", "schema", "id"],
                                name="shop_convrecord_latest")]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "environment", "record_id"],
                                    name="shop_convrecord_unique_id"),
            models.UniqueConstraint(fields=["tenant", "environment", "dedupe_key"],
                                    name="shop_convrecord_unique_event"),
        ]


class ConversationalWork(models.Model):
    """A caixa de saída do framework: trabalho gravado na mesma transação do estado (N13)."""

    tenant = models.CharField("inquilino", max_length=64)
    environment = models.CharField("ambiente", max_length=16)
    work_id = models.CharField("trabalho", max_length=256)
    kind = models.CharField("tipo", max_length=64)
    payload = models.JSONField("carga", default=dict)
    due_at = models.DateTimeField("vence em")
    lease_until = models.DateTimeField("reivindicado até", null=True, blank=True)
    attempt = models.PositiveIntegerField("tentativa", default=0)
    created_at = models.DateTimeField("criado em", auto_now_add=True)

    class Meta:
        app_label = "shop"
        verbose_name = "trabalho conversacional"
        verbose_name_plural = "trabalhos conversacionais"
        indexes = [models.Index(fields=["tenant", "environment", "kind", "due_at"], name="shop_convwork_due")]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "environment", "work_id"], name="shop_convwork_unique_id"),
        ]
