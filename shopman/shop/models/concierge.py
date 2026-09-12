"""Concierge: a conversa lógica, seus transportes e as mensagens que guarda.

Uma ``Conversation`` carrega o que a casa precisa lembrar ENTRE turnos e que o
modelo não pode inventar: quem é o cliente (telefone, ref), a sacola aberta
(``session_key``), o último orçamento apresentado (``quote``) e se a conversa
está com a equipe (``state``).

Cada ``ConversationBinding`` liga essa memória lógica a um endereço opaco de
transporte. Assim, uma troca de fornecedor ou um canal adicional não duplica a
sacola nem perde a transcrição.

As ``ConversationMessage`` são a transcrição no formato em que o modelo as
recebe de volta: blocos de conteúdo (texto, chamada e resultado de
ferramenta), na ordem. Guardar o formato de replay evita uma segunda
tradução, e é a transcrição que o gestor lê no Admin.

Nada de regra de pedido mora aqui. Preço, estoque, prazo e pagamento são das
ferramentas em ``shopman/storefront/concierge/tools.py``, que só chamam services.
"""

from __future__ import annotations

from django.db import models
from django.db.models import Q
from django.utils import timezone


class Conversation(models.Model):
    class State(models.TextChoices):
        ACTIVE = "active", "Ativa"
        HANDOFF = "handoff", "Com a equipe"
        CLOSED = "closed", "Encerrada"

    turn_fence = models.PositiveBigIntegerField("versão de controle do turno", default=0)
    claim_until = models.DateTimeField("posse do turno até", null=True, blank=True)
    last_order_ref = models.CharField("referência do último pedido", max_length=64, blank=True)
    #: E.164 com "+", comprovado pelo adapter. Vazio = identidade sem telefone:
    #: pode conversar, mas não pode executar uma compra.
    phone = models.CharField("telefone", max_length=32, blank=True)
    customer_ref = models.CharField("ref do cliente", max_length=64, blank=True)
    customer_name = models.CharField("nome do cliente", max_length=120, blank=True)
    channel_ref = models.CharField("canal de venda", max_length=64, default="whatsapp")

    state = models.CharField("estado", max_length=16, choices=State.choices, default=State.ACTIVE)
    handoff_reason = models.CharField("motivo do handoff", max_length=200, blank=True)
    handoff_at = models.DateTimeField("handoff em", null=True, blank=True)

    #: Sacola aberta (Orderman `Session.session_key`) no canal do concierge.
    session_key = models.CharField("sacola", max_length=64, blank=True)
    #: Último orçamento apresentado ao cliente: ``{token, total_q, lines, fulfillment,
    #: issued_at}``. O ``place_order`` só aceita o token do orçamento VIGENTE; a sacola
    #: mudou, o token muda, e o pedido volta para a revisão.
    quote = models.JSONField("orçamento vigente", default=dict, blank=True)

    #: O que a casa já fez nesta conversa e não repete: ``{"suggestion_offered": true}``
    #: (o adicional é UM por conversa, não um por recap).
    flags = models.JSONField("marcas da conversa", default=dict, blank=True)

    #: Resumo das mensagens antigas que saíram da janela enviada ao modelo.
    summary = models.TextField("resumo", blank=True)
    summary_until_id = models.BigIntegerField("resumo cobre até", null=True, blank=True)

    turns_day = models.DateField("dia dos turnos", null=True, blank=True)
    turns_today = models.IntegerField("turnos no dia", default=0)
    consecutive_failures = models.IntegerField("falhas seguidas", default=0)

    input_tokens = models.BigIntegerField("tokens de entrada", default=0)
    output_tokens = models.BigIntegerField("tokens de saída", default=0)
    cache_read_tokens = models.BigIntegerField("tokens lidos do cache", default=0)

    last_inbound_at = models.DateTimeField("última mensagem do cliente", null=True, blank=True)
    last_outbound_at = models.DateTimeField("última resposta", null=True, blank=True)
    created_at = models.DateTimeField("criada em", auto_now_add=True)
    updated_at = models.DateTimeField("atualizada em", auto_now=True)

    class Meta:
        verbose_name = "conversa do concierge"
        verbose_name_plural = "conversas do concierge"
        ordering = ("-last_inbound_at", "-id")
        indexes = [
            models.Index(fields=["state", "last_inbound_at"], name="shop_conv_state_inbound_idx"),
            models.Index(fields=["customer_ref"], name="shop_conv_customer_idx"),
        ]

    def __str__(self) -> str:
        who = self.customer_name or self.phone or self.customer_ref or f"#{self.pk}"
        return f"Conversa {self.pk} · {who}"

    @property
    def is_with_team(self) -> bool:
        return self.state == self.State.HANDOFF


class ConversationBinding(models.Model):
    """Endereço de transporte de uma conversa, sem credenciais do fornecedor."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pendente"
        ACTIVE = "active", "Ativo"
        DISABLED = "disabled", "Desativado"

    class IdentityAssurance(models.TextChoices):
        UNVERIFIED = "unverified", "Sem verificação"
        TRANSPORT_SUBJECT = "transport_subject", "Endereço autenticado do transporte"
        CONFIGURED_TRANSPORT = "configured_transport", "Escopo configurado"
        VERIFIED_CUSTOMER = "verified_customer", "Cliente verificado"

    conversation = models.ForeignKey(
        Conversation,
        on_delete=models.PROTECT,
        related_name="transport_bindings",
        verbose_name="conversa",
    )
    provider = models.CharField("provedor", max_length=40)
    account = models.CharField("conta do provedor", max_length=128)
    transport_channel = models.CharField("canal de comunicação", max_length=40)
    subject = models.CharField("identificador no transporte", max_length=512)
    connection_key = models.CharField("conexão configurada", max_length=80)
    status = models.CharField("estado", max_length=16, choices=Status.choices, default=Status.PENDING)
    identity_assurance = models.CharField(
        "garantia de identidade",
        max_length=32,
        choices=IdentityAssurance.choices,
        default=IdentityAssurance.UNVERIFIED,
    )
    handoff_sync_state = models.CharField("sincronização do atendimento humano", max_length=24, default="not_applied")
    last_inbound_at = models.DateTimeField("última mensagem recebida", null=True, blank=True)
    last_outbound_at = models.DateTimeField("última resposta enviada", null=True, blank=True)
    activated_at = models.DateTimeField("ativado em", null=True, blank=True)
    deactivated_at = models.DateTimeField("desativado em", null=True, blank=True)
    created_at = models.DateTimeField("criado em", auto_now_add=True)
    updated_at = models.DateTimeField("atualizado em", auto_now=True)

    class Meta:
        verbose_name = "vínculo de transporte do concierge"
        verbose_name_plural = "vínculos de transporte do concierge"
        ordering = ("conversation_id", "transport_channel", "id")
        constraints = [
            models.UniqueConstraint(
                fields=["provider", "account", "transport_channel", "subject"],
                name="shop_cbind_identity_unique",
            ),
            models.UniqueConstraint(
                fields=["conversation", "transport_channel"],
                condition=Q(status="active"),
                name="shop_cbind_active_channel_unique",
            ),
            models.CheckConstraint(
                condition=(
                    ~Q(provider="") & ~Q(account="") & ~Q(transport_channel="") & ~Q(subject="") & ~Q(connection_key="")
                ),
                name="shop_cbind_identity_not_blank",
            ),
        ]
        indexes = [
            models.Index(fields=["conversation", "status"], name="shop_cbind_conv_status_idx"),
            models.Index(fields=["status", "last_inbound_at"], name="shop_cbind_status_in_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.provider}/{self.transport_channel} · {self.subject}"


class ConversationMessage(models.Model):
    class Role(models.TextChoices):
        USER = "user", "Cliente"
        ASSISTANT = "assistant", "Concierge"

    class Kind(models.TextChoices):
        INBOUND = "inbound", "Mensagem do cliente"
        REPLY = "reply", "Resposta"
        TOOL_CALL = "tool_call", "Chamada de ferramenta"
        TOOL_RESULT = "tool_result", "Resultado de ferramenta"
        NOTE = "note", "Nota da casa"

    conversation = models.ForeignKey(
        Conversation, on_delete=models.CASCADE, related_name="messages", verbose_name="conversa"
    )
    binding = models.ForeignKey(
        ConversationBinding,
        on_delete=models.PROTECT,
        related_name="messages",
        verbose_name="vínculo de transporte",
        null=True,
        blank=True,
    )
    #: Papel no replay para o modelo. Resultado de ferramenta viaja como ``user``,
    #: chamada de ferramenta como ``assistant`` (formato da API).
    role = models.CharField("papel", max_length=16, choices=Role.choices)
    kind = models.CharField("tipo", max_length=16, choices=Kind.choices)
    #: Texto legível (a mensagem do cliente, a resposta enviada). Vazio em
    #: chamadas/resultados de ferramenta, que vivem em ``content``.
    text = models.TextField("texto", blank=True)
    #: Blocos de conteúdo no formato da API (text / tool_use / tool_result).
    content = models.JSONField("conteúdo", default=list, blank=True)
    #: Digest estável do ID externo íntegro guardado no envelope v3.
    external_id = models.CharField("id externo", max_length=80, blank=True)
    consumed_by = models.PositiveBigIntegerField("turno que processou a entrada", null=True, blank=True, db_index=True)
    #: Projeção operacional atual. A evidência de cada execução é append-only em
    #: ``OutboundAttempt``; receipt do fornecedor nunca é sobrescrito aqui.
    transport_state = models.CharField("estado do envio", max_length=24, default="not_applicable", db_index=True)
    envelope = models.JSONField("envelope de transporte", default=dict, blank=True)
    usage = models.JSONField("consumo", default=dict, blank=True)
    created_at = models.DateTimeField("criada em", auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = "mensagem do concierge"
        verbose_name_plural = "mensagens do concierge"
        ordering = ("id",)
        constraints = [
            models.UniqueConstraint(
                fields=["binding", "external_id"],
                condition=~Q(external_id=""),
                name="shop_cmsg_binding_event_unique",
            ),
            models.CheckConstraint(
                condition=(Q(kind__in=["tool_call", "tool_result", "note"]) | Q(binding__isnull=False)),
                name="shop_cmsg_transport_binding_required",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.get_kind_display()} #{self.pk}"


class OutboundAttempt(models.Model):
    """Evidência append-only de saída, subordinada à projeção da mensagem.

    ``ConversationMessage.transport_state`` responde rapidamente pelo estado
    atual. Esta tabela conserva cada execução e o receipt imutável necessário
    para reconciliar callbacks do fornecedor sem sobrescrever história.
    """

    class State(models.TextChoices):
        EXECUTING = "executing", "Em execução"
        ACCEPTED = "accepted", "Aceita pelo fornecedor"
        NOT_APPLIED = "not_applied", "Não aplicada"
        UNKNOWN = "unknown", "Resultado desconhecido"
        DELIVERED = "delivered", "Entregue"
        READ = "read", "Lida"

    message = models.ForeignKey(
        ConversationMessage,
        on_delete=models.PROTECT,
        related_name="outbound_attempts",
        verbose_name="mensagem",
    )
    binding = models.ForeignKey(
        ConversationBinding,
        on_delete=models.PROTECT,
        related_name="outbound_attempts",
        verbose_name="vínculo de transporte",
    )
    attempt_no = models.PositiveIntegerField("número da tentativa")
    state = models.CharField("estado", max_length=24, choices=State.choices, default=State.EXECUTING)
    code = models.CharField("código do resultado", max_length=80, blank=True)
    provider_receipt_ref = models.CharField("referência no provedor", max_length=512, blank=True)
    payload_hash = models.CharField("hash do conteúdo", max_length=64)
    started_at = models.DateTimeField("iniciada em", default=timezone.now)
    completed_at = models.DateTimeField("concluída em", null=True, blank=True)

    class Meta:
        verbose_name = "tentativa de saída do concierge"
        verbose_name_plural = "tentativas de saída do concierge"
        ordering = ("message_id", "attempt_no")
        constraints = [
            models.UniqueConstraint(
                fields=["message", "attempt_no"],
                name="shop_cattempt_message_no_unique",
            ),
            models.UniqueConstraint(
                fields=["binding", "provider_receipt_ref"],
                condition=~Q(provider_receipt_ref=""),
                name="shop_cattempt_binding_receipt_unique",
            ),
            models.CheckConstraint(
                condition=Q(attempt_no__gte=1),
                name="shop_cattempt_no_positive",
            ),
        ]

    def __str__(self) -> str:
        return f"Saída #{self.message_id}.{self.attempt_no} · {self.state}"
