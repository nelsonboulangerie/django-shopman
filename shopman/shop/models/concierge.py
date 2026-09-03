"""Concierge de WhatsApp: a conversa e as mensagens que ela guarda.

Uma ``Conversation`` por assinante do ManyChat. Ela carrega o que a casa
precisa lembrar ENTRE turnos e que o modelo não pode inventar: quem é o
cliente (telefone, ref), a sacola aberta (``session_key``), o último orçamento
apresentado (``quote``) e se a conversa está com a equipe (``state``).

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


class Conversation(models.Model):
    class State(models.TextChoices):
        ACTIVE = "active", "Ativa"
        HANDOFF = "handoff", "Com a equipe"
        CLOSED = "closed", "Encerrada"

    #: `subscriber_id` do ManyChat: a única identidade que o flow nunca erra.
    subscriber_id = models.CharField("assinante ManyChat", max_length=32, unique=True)
    #: E.164 com "+", vindo do `getInfo` (campo `whatsapp_phone`). Vazio = contato
    #: sem telefone (chegou pelo Instagram): pode conversar, não pode pedir.
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
        who = self.customer_name or self.phone or self.subscriber_id
        return f"Conversa {self.pk} · {who}"

    @property
    def is_with_team(self) -> bool:
        return self.state == self.State.HANDOFF


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
    #: Papel no replay para o modelo. Resultado de ferramenta viaja como ``user``,
    #: chamada de ferramenta como ``assistant`` (formato da API).
    role = models.CharField("papel", max_length=16, choices=Role.choices)
    kind = models.CharField("tipo", max_length=16, choices=Kind.choices)
    #: Texto legível (a mensagem do cliente, a resposta enviada). Vazio em
    #: chamadas/resultados de ferramenta, que vivem em ``content``.
    text = models.TextField("texto", blank=True)
    #: Blocos de conteúdo no formato da API (text / tool_use / tool_result).
    content = models.JSONField("conteúdo", default=list, blank=True)
    #: Id externo da mensagem inbound (ou hash), para não responder duas vezes ao
    #: mesmo evento quando o ManyChat reenvia.
    external_id = models.CharField("id externo", max_length=80, blank=True)
    #: Para respostas: o envio pelo ManyChat foi aceito? ``None`` = não enviada
    #: (nota interna, ferramenta), ``False`` = recusa registrada no log.
    delivered = models.BooleanField("entregue", null=True, blank=True)
    usage = models.JSONField("consumo", default=dict, blank=True)
    created_at = models.DateTimeField("criada em", auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = "mensagem do concierge"
        verbose_name_plural = "mensagens do concierge"
        ordering = ("id",)
        constraints = [
            models.UniqueConstraint(
                fields=["conversation", "external_id"],
                condition=~Q(external_id=""),
                name="shop_convmsg_external_id_unique",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.get_kind_display()} #{self.pk}"
