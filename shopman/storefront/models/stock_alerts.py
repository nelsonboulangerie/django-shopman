"""Persistent customer alert subscriptions, occurrences and delivery receipts.

Customer-facing: a shopper (logged-in OR anonymous with just a phone) asks to be
notified about a SKU. Dois gatilhos, um modelo:

- ``stock_back``      — o SKU esgotado voltou ao estoque
- ``production_ready`` — saiu uma fornada nova (F9 do FOMO-MARKETING-SPECS)

The subscription is the customer's durable opt-in.  An occurrence identifies one
real-world transition/bake and a delivery receipt makes that occurrence idempotent.
"""

from __future__ import annotations

import uuid

from django.db import models
from django.db.models import Q
from django.utils import timezone
from shopman.utils.refs import RefField


class StockAlertSubscriptionQuerySet(models.QuerySet):
    def active(self, *, now=None):
        now = now or timezone.now()
        return self.filter(
            revoked_at__isnull=True,
            paused_at__isnull=True,
            proof_status="verified",
        ).filter(Q(expires_at__isnull=True) | Q(expires_at__gt=now))


class StockAlertSubscription(models.Model):
    """Persistent "notify me" opt-in for one SKU, event and contact.

    Anonymous subscribers carry only ``contact_phone``; authenticated ones carry
    ``customer_ref`` (and usually a phone too). ``notified_at`` is retained as a
    compatibility/last-delivery timestamp; it never consumes the subscription.
    """

    class AlertType(models.TextChoices):
        STOCK_BACK = "stock_back", "voltou ao estoque"
        PRODUCTION_READY = "production_ready", "saiu do forno"

    ref = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    sku = RefField(ref_type="SKU", max_length=64, db_index=True)
    alert_type = models.CharField(
        verbose_name="tipo de aviso",
        max_length=24,
        choices=AlertType.choices,
        default=AlertType.STOCK_BACK,
    )
    channel_ref = models.CharField(verbose_name="ref do canal", max_length=32, default="web")
    delivery_channel = models.CharField(verbose_name="canal de entrega", max_length=20, default="whatsapp")
    purpose = models.CharField(verbose_name="finalidade", max_length=32, default="stock_availability")
    customer_ref = models.CharField(verbose_name="ref do cliente", max_length=64, blank=True, default="")
    contact_phone = models.CharField(verbose_name="telefone de contato", max_length=32, blank=True, default="")
    target_key = models.CharField(verbose_name="identificador protegido", max_length=64, db_index=True)
    disclosure_text = models.TextField(verbose_name="texto apresentado", blank=True)
    disclosure_version = models.CharField(verbose_name="versão do texto", max_length=64, blank=True)
    disclosure_hash = models.CharField(verbose_name="hash do texto", max_length=64, blank=True)
    evidence_hash = models.CharField(verbose_name="hash da evidência", max_length=64, unique=True)
    proof_status = models.CharField(
        verbose_name="situação da prova",
        max_length=24,
        choices=[("verified", "verificada"), ("legacy_unverified", "legado sem prova completa")],
        default="legacy_unverified",
    )
    subscribed_at = models.DateTimeField(verbose_name="pedido em", auto_now_add=True)
    dispatch_claimed_at = models.DateTimeField(verbose_name="envio assumido em", null=True, blank=True)
    dispatch_accepted_at = models.DateTimeField(verbose_name="envio aceito em", null=True, blank=True)
    notified_at = models.DateTimeField(verbose_name="avisado em", null=True, blank=True)
    expires_at = models.DateTimeField(verbose_name="expira em", null=True, blank=True)
    revoked_at = models.DateTimeField(verbose_name="cancelado em", null=True, blank=True)
    revoke_reason = models.CharField(verbose_name="motivo do cancelamento", max_length=100, blank=True)
    revocation_evidence_hash = models.CharField(verbose_name="hash da revogação", max_length=64, blank=True)
    paused_at = models.DateTimeField(verbose_name="pausado em", null=True, blank=True)
    pause_reason = models.CharField(verbose_name="motivo da pausa", max_length=100, blank=True, db_default="")

    objects = StockAlertSubscriptionQuerySet.as_manager()

    class Meta:
        app_label = "storefront"
        verbose_name = "aviso de reposição"
        verbose_name_plural = "avisos de reposição"
        indexes = [
            models.Index(fields=["sku", "notified_at"]),
            models.Index(fields=["sku", "alert_type", "notified_at"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["sku", "alert_type", "channel_ref", "target_key"],
                condition=Q(revoked_at__isnull=True),
                name="storefront_stock_alert_active_target_uq",
            ),
        ]

    def __str__(self) -> str:  # pragma: no cover - admin/debug only
        who = self.customer_ref or self.contact_phone or "?"
        state = "active" if self.is_active else "inactive"
        return f"StockAlert({self.sku}/{self.alert_type} → {who}, {state})"

    @property
    def is_active(self) -> bool:
        return (
            self.revoked_at is None
            and self.paused_at is None
            and self.proof_status == "verified"
            and (self.expires_at is None or self.expires_at > timezone.now())
        )

    @property
    def is_pending(self) -> bool:
        """Compatibility alias for callers that mean an active opt-in."""
        return self.is_active


class StockAlertOccurrence(models.Model):
    """One durable, semantically deduplicated product event."""

    class Status(models.TextChoices):
        PENDING = "pending", "aguardando validação"
        ELIGIBLE = "eligible", "elegível"
        BLOCKED = "blocked", "bloqueada"
        CLOSED = "closed", "encerrada"

    ref = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    sku = RefField(ref_type="SKU", max_length=64, db_index=True)
    event_type = models.CharField(
        verbose_name="tipo de ocorrência",
        max_length=24,
        choices=StockAlertSubscription.AlertType.choices,
    )
    channel_ref = models.CharField(verbose_name="ref do canal", max_length=32, default="web")
    semantic_key = models.CharField(verbose_name="chave semântica", max_length=160, unique=True)
    source_ref = models.CharField(verbose_name="referência de origem", max_length=100, blank=True)
    status = models.CharField(
        verbose_name="situação",
        max_length=16,
        choices=Status.choices,
        default=Status.PENDING,
    )
    status_reason = models.CharField(verbose_name="motivo da situação", max_length=100, blank=True)
    available_qty = models.DecimalField(
        verbose_name="quantidade disponível",
        max_digits=12,
        decimal_places=3,
        null=True,
        blank=True,
    )
    closed_at = models.DateTimeField(verbose_name="encerrada em", null=True, blank=True)
    created_at = models.DateTimeField(verbose_name="criada em", auto_now_add=True)
    updated_at = models.DateTimeField(verbose_name="atualizada em", auto_now=True)

    class Meta:
        app_label = "storefront"
        verbose_name = "ocorrência de aviso de produto"
        verbose_name_plural = "ocorrências de avisos de produto"
        indexes = [models.Index(fields=["sku", "event_type", "closed_at"])]
        constraints = [
            models.UniqueConstraint(
                fields=["sku", "event_type", "channel_ref"],
                condition=Q(event_type="stock_back", closed_at__isnull=True),
                name="storefront_stock_alert_open_cycle_uq",
            )
        ]

    def __str__(self) -> str:  # pragma: no cover - admin/debug only
        return f"{self.sku} · {self.get_event_type_display()} · {self.get_status_display()}"


class StockAlertDelivery(models.Model):
    """Receipt for one subscription and one occurrence."""

    class Status(models.TextChoices):
        QUEUED = "queued", "na fila"
        CLAIMED = "claimed", "em envio"
        ACCEPTED = "accepted", "aceita"
        RETRYABLE = "retryable", "tentar novamente"
        INDETERMINATE = "indeterminate", "resultado incerto"
        SUPPRESSED = "suppressed", "suprimida"

    ref = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    subscription = models.ForeignKey(
        StockAlertSubscription,
        verbose_name="assinatura",
        on_delete=models.CASCADE,
        related_name="deliveries",
    )
    occurrence = models.ForeignKey(
        StockAlertOccurrence,
        verbose_name="ocorrência",
        on_delete=models.CASCADE,
        related_name="deliveries",
    )
    purpose = models.CharField(verbose_name="finalidade", max_length=32, default="stock_availability")
    delivery_channel = models.CharField(verbose_name="canal de entrega", max_length=20, default="whatsapp")
    status = models.CharField(
        verbose_name="situação",
        max_length=20,
        choices=Status.choices,
        default=Status.QUEUED,
    )
    directive_id = models.BigIntegerField(verbose_name="id da diretiva", null=True, blank=True, db_index=True)
    claimed_at = models.DateTimeField(verbose_name="assumida em", null=True, blank=True)
    accepted_at = models.DateTimeField(verbose_name="aceita em", null=True, blank=True)
    provider_receipt_ref = models.CharField(verbose_name="referência no provedor", max_length=160, blank=True)
    last_error_code = models.CharField(verbose_name="código do último erro", max_length=100, blank=True)
    created_at = models.DateTimeField(verbose_name="criada em", auto_now_add=True)
    updated_at = models.DateTimeField(verbose_name="atualizada em", auto_now=True)

    class Meta:
        app_label = "storefront"
        verbose_name = "entrega de aviso de produto"
        verbose_name_plural = "entregas de avisos de produto"
        indexes = [models.Index(fields=["status", "created_at"])]
        constraints = [
            models.UniqueConstraint(
                fields=["subscription", "occurrence", "purpose", "delivery_channel"],
                name="storefront_stock_alert_delivery_uq",
            )
        ]

    def __str__(self) -> str:  # pragma: no cover - admin/debug only
        return f"{self.occurrence} · {self.get_status_display()}"
