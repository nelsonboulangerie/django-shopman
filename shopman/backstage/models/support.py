"""Suporte: ticket interno, mensagens e decisão.

O ticket nasce com o contexto que o sistema já tem (ADR-045) e o texto do
requester. A classificação é sugestão; o estado e a aprovação são determinísticos.
O compromisso de dev vive no ledger (`DEV-`), não aqui: este modelo guarda o
registro do Suporte e aponta para ele.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone


class SupportTicket(models.Model):
    """Chamado do Suporte (dúvida, queixa, bug, pedido, ideia, decisão)."""

    AUDIENCE_INTERNAL = "internal"
    AUDIENCE_EXTERNAL = "external"
    AUDIENCE_CHOICES = [
        (AUDIENCE_INTERNAL, "Interno"),
        (AUDIENCE_EXTERNAL, "Externo"),
    ]

    TYPE_QUESTION = "question"
    TYPE_COMPLAINT = "complaint"
    TYPE_BUG = "bug"
    TYPE_REQUEST = "request"
    TYPE_IDEA = "idea"
    TYPE_DECISION = "decision"
    TYPE_CHOICES = [
        (TYPE_QUESTION, "Dúvida"),
        (TYPE_COMPLAINT, "Queixa"),
        (TYPE_BUG, "Defeito"),
        (TYPE_REQUEST, "Pedido"),
        (TYPE_IDEA, "Ideia"),
        (TYPE_DECISION, "Decisão"),
    ]

    STATUS_NEW = "new"
    STATUS_TRIAGE = "triage"
    STATUS_WAITING_REQUESTER = "waiting_requester"
    STATUS_WAITING_OWNER = "waiting_owner"
    STATUS_APPROVED = "approved"
    STATUS_REJECTED = "rejected"
    STATUS_IN_DEV = "in_dev"
    STATUS_RESOLVED = "resolved"
    STATUS_CLOSED = "closed"
    STATUS_DEFERRED = "deferred"
    STATUS_CHOICES = [
        (STATUS_NEW, "Novo"),
        (STATUS_TRIAGE, "Em triagem"),
        (STATUS_WAITING_REQUESTER, "Aguardando quem abriu"),
        (STATUS_WAITING_OWNER, "Aguardando o dono"),
        (STATUS_APPROVED, "Aprovado"),
        (STATUS_REJECTED, "Recusado"),
        (STATUS_IN_DEV, "Em desenvolvimento"),
        (STATUS_RESOLVED, "Resolvido"),
        (STATUS_CLOSED, "Fechado"),
        (STATUS_DEFERRED, "Adiado"),
    ]
    OPEN_STATUSES = (
        STATUS_NEW,
        STATUS_TRIAGE,
        STATUS_WAITING_REQUESTER,
        STATUS_WAITING_OWNER,
        STATUS_APPROVED,
        STATUS_IN_DEV,
        STATUS_DEFERRED,
    )

    PRIORITY_LOW = "low"
    PRIORITY_NORMAL = "normal"
    PRIORITY_HIGH = "high"
    PRIORITY_URGENT = "urgent"
    PRIORITY_CHOICES = [
        (PRIORITY_LOW, "Baixa"),
        (PRIORITY_NORMAL, "Normal"),
        (PRIORITY_HIGH, "Alta"),
        (PRIORITY_URGENT, "Urgente"),
    ]

    ref = models.CharField(
        "referência",
        max_length=20,
        unique=True,
        null=True,
        blank=True,
        editable=False,
    )
    audience = models.CharField(
        "público",
        max_length=16,
        choices=AUDIENCE_CHOICES,
        default=AUDIENCE_INTERNAL,
    )
    type = models.CharField(
        "tipo",
        max_length=16,
        choices=TYPE_CHOICES,
        default=TYPE_QUESTION,
    )
    status = models.CharField(
        "estado",
        max_length=24,
        choices=STATUS_CHOICES,
        default=STATUS_NEW,
    )
    priority = models.CharField(
        "prioridade",
        max_length=12,
        choices=PRIORITY_CHOICES,
        default=PRIORITY_NORMAL,
    )
    subject = models.CharField("assunto", max_length=200, blank=True)
    description = models.TextField("descrição")
    context = models.JSONField(
        "contexto",
        default=dict,
        blank=True,
        help_text="Envelope operacional da ADR-045. Refs, nunca PII.",
    )
    client_uuid = models.UUIDField(
        "uuid do cliente",
        null=True,
        blank=True,
        unique=True,
        help_text="Idempotência do ticket criado offline.",
    )
    requester = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="support_tickets",
        verbose_name="quem abriu",
    )
    requester_role = models.CharField("papel de quem abriu", max_length=20, blank=True)
    assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_support_tickets",
        verbose_name="responsável",
    )
    sla_due = models.DateTimeField("prazo de atendimento", null=True, blank=True)
    review_at = models.DateField("revisar em", null=True, blank=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_support_tickets",
        verbose_name="aprovado por",
    )
    approved_at = models.DateTimeField("aprovado em", null=True, blank=True)
    approval_basis = models.CharField("fundamento da aprovação", max_length=200, blank=True)
    ledger_ref = models.CharField(
        "compromisso de dev",
        max_length=20,
        blank=True,
        help_text="Linha DEV-0000 do ledger, quando o pedido vira código.",
    )
    resolution = models.TextField("resolução", blank=True)
    created_at = models.DateTimeField("criado em", auto_now_add=True)
    updated_at = models.DateTimeField("atualizado em", auto_now=True)
    closed_at = models.DateTimeField("fechado em", null=True, blank=True)

    class Meta:
        verbose_name = "chamado do Suporte"
        verbose_name_plural = "chamados do Suporte"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "updated_at"]),
            models.Index(fields=["assignee", "status"]),
            models.Index(fields=["requester", "created_at"]),
            models.Index(fields=["type", "status"]),
        ]

    def __str__(self) -> str:
        return f"{self.ref or 'HELP-?'} · {self.subject or self.description[:40]}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if not self.ref:
            self.ref = f"HELP-{self.pk:04d}"
            super().save(update_fields=["ref"])

    @property
    def is_open(self) -> bool:
        return self.status in self.OPEN_STATUSES

    def close(self, resolution: str = "") -> None:
        self.status = self.STATUS_CLOSED
        self.resolution = resolution or self.resolution
        self.closed_at = timezone.now()
        self.save(update_fields=["status", "resolution", "closed_at", "updated_at"])


class SupportMessage(models.Model):
    """Mensagem da thread. Interna não aparece para quem abriu."""

    CHANNEL_HUB = "hub"
    CHANNEL_TELEGRAM = "telegram"
    CHANNEL_WHATSAPP = "whatsapp"
    CHANNEL_EMAIL = "email"
    CHANNEL_CHOICES = [
        (CHANNEL_HUB, "Central"),
        (CHANNEL_TELEGRAM, "Telegram"),
        (CHANNEL_WHATSAPP, "WhatsApp"),
        (CHANNEL_EMAIL, "E-mail"),
    ]

    ticket = models.ForeignKey(
        SupportTicket,
        on_delete=models.CASCADE,
        related_name="messages",
        verbose_name="chamado",
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="support_messages",
        verbose_name="autor",
    )
    body = models.TextField("mensagem")
    internal_note = models.BooleanField(
        "nota interna",
        default=False,
        help_text="Nota da equipe; não aparece para quem abriu.",
    )
    channel = models.CharField(
        "canal",
        max_length=16,
        choices=CHANNEL_CHOICES,
        default=CHANNEL_HUB,
    )
    ai_meta = models.JSONField(
        "metadados da IA",
        default=dict,
        blank=True,
        help_text="Sugestão de triagem/resumo (ID3A), quando houver.",
    )
    created_at = models.DateTimeField("criada em", auto_now_add=True)

    class Meta:
        verbose_name = "mensagem do Suporte"
        verbose_name_plural = "mensagens do Suporte"
        ordering = ["created_at"]
        indexes = [models.Index(fields=["ticket", "created_at"])]

    def __str__(self) -> str:
        return f"{self.ticket_id} · {self.body[:40]}"


class SupportDecision(models.Model):
    """Decisão do dono sobre um pedido. Append-only."""

    DECISION_APPROVE = "approve"
    DECISION_REJECT = "reject"
    DECISION_DEFER = "defer"
    DECISION_CHOICES = [
        (DECISION_APPROVE, "Aprovar"),
        (DECISION_REJECT, "Recusar"),
        (DECISION_DEFER, "Adiar"),
    ]

    ticket = models.ForeignKey(
        SupportTicket,
        on_delete=models.CASCADE,
        related_name="decisions",
        verbose_name="chamado",
    )
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="support_decisions",
        verbose_name="decidido por",
    )
    decision = models.CharField("decisão", max_length=12, choices=DECISION_CHOICES)
    reason = models.TextField("motivo", blank=True)
    created_at = models.DateTimeField("decidida em", auto_now_add=True)

    class Meta:
        verbose_name = "decisão do Suporte"
        verbose_name_plural = "decisões do Suporte"
        ordering = ["created_at"]
        indexes = [models.Index(fields=["ticket", "created_at"])]

    def __str__(self) -> str:
        return f"{self.ticket_id} · {self.decision}"
