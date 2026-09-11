"""Alert subscriptions do cliente ("Me avise quando…").

Customer-facing: a shopper (logged-in OR anonymous with just a phone) asks to be
notified about a SKU. Dois gatilhos, um modelo:

- ``stock_back``      — o SKU esgotado voltou ao estoque
- ``production_ready`` — saiu uma fornada nova (F9 do FOMO-MARKETING-SPECS)

O segundo não exige que o produto esteja esgotado: quem quer pão quente quer
saber da fornada, não da reposição. Ambos são idempotentes via ``notified_at``.
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
            notified_at__isnull=True,
            revoked_at__isnull=True,
            proof_status="verified",
        ).filter(Q(expires_at__isnull=True) | Q(expires_at__gt=now))


class StockAlertSubscription(models.Model):
    """One pending "notify me" request for a SKU.

    Anonymous subscribers carry only ``contact_phone``; authenticated ones carry
    ``customer_ref`` (and usually a phone too). A subscription is *pending* until
    ``notified_at`` is set.
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
    dispatch_claimed_at = models.DateTimeField(null=True, blank=True)
    dispatch_accepted_at = models.DateTimeField(null=True, blank=True)
    notified_at = models.DateTimeField(verbose_name="avisado em", null=True, blank=True)
    expires_at = models.DateTimeField(verbose_name="expira em", null=True, blank=True)
    revoked_at = models.DateTimeField(verbose_name="cancelado em", null=True, blank=True)
    revoke_reason = models.CharField(verbose_name="motivo do cancelamento", max_length=100, blank=True)
    revocation_evidence_hash = models.CharField(
        verbose_name="hash da revogação", max_length=64, blank=True
    )

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
                condition=Q(notified_at__isnull=True, revoked_at__isnull=True),
                name="storefront_stock_alert_pending_target_uq",
            ),
        ]

    def __str__(self) -> str:  # pragma: no cover - admin/debug only
        who = self.customer_ref or self.contact_phone or "?"
        state = "pending" if self.notified_at is None else "notified"
        return f"StockAlert({self.sku}/{self.alert_type} → {who}, {state})"

    @property
    def is_pending(self) -> bool:
        return (
            self.notified_at is None
            and self.revoked_at is None
            and self.proof_status == "verified"
            and (self.expires_at is None or self.expires_at > timezone.now())
        )
