"""Consent projection and append-only evidence for customer communications."""

from __future__ import annotations

import uuid

from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _


class ConsentChannel(models.TextChoices):
    """Communication channels requiring consent."""

    WHATSAPP = "whatsapp", _("WhatsApp")
    EMAIL = "email", _("Email")
    SMS = "sms", _("SMS")
    PUSH = "push", _("Push Notification")


class ConsentStatus(models.TextChoices):
    """Consent states."""

    OPTED_IN = "opted_in", _("Opt-in")
    OPTED_OUT = "opted_out", _("Opt-out")
    PENDING = "pending", _("Pendente")


class LegalBasis(models.TextChoices):
    """LGPD legal basis for data processing."""

    CONSENT = "consent", _("Consentimento")
    LEGITIMATE_INTEREST = "legitimate_interest", _("Interesse legítimo")
    CONTRACT = "contract", _("Execução de contrato")
    LEGAL_OBLIGATION = "legal_obligation", _("Obrigação legal")


class ConsentPurpose(models.TextChoices):
    """Purpose limitation agreed in marketing-human-gates.v1."""

    MARKETING_GENERAL = "marketing_general", _("Marketing geral")
    STOCK_AVAILABILITY = "stock_availability", _("Disponibilidade de produto")
    TRANSACTIONAL_ORDER = "transactional_order", _("Comunicação do pedido")


class ConsentProofStatus(models.TextChoices):
    """Whether an opt-in has the evidence required for marketing use."""

    VERIFIED = "verified", _("Verificado")
    LEGACY_UNVERIFIED = "legacy_unverified", _("Legado sem prova completa")


class ConsentEventType(models.TextChoices):
    GRANTED = "granted", _("Concedido")
    REVOKED = "revoked", _("Revogado")
    LEGACY_IMPORT = "legacy_import", _("Importado do legado")


class _AppendOnlyConsentEventQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise ValidationError(_("Eventos de consentimento são imutáveis."))

    def delete(self):
        raise ValidationError(_("Eventos de consentimento não podem ser apagados."))


class CommunicationConsent(models.Model):
    """
    Per-channel communication consent for a customer.

    LGPD requires explicit, informed, and revocable consent for
    marketing communications. This model tracks:
    - Which channels the customer opted into/out of
    - When consent was granted or revoked
    - The source (how consent was collected)
    - Legal basis for processing

    Rules:
    - One record per (customer, channel)
    - Default status is 'pending' (no communication until opted_in)
    - Revocation is immediate and logged
    - Audit trail preserved (consented_at, revoked_at)
    """

    customer = models.ForeignKey(
        "guestman.Customer",
        on_delete=models.CASCADE,
        related_name="consents",
        verbose_name=_("cliente"),
    )

    channel = models.CharField(
        _("canal"),
        max_length=20,
        choices=ConsentChannel.choices,
        db_index=True,
    )
    purpose = models.CharField(
        _("finalidade"),
        max_length=32,
        choices=ConsentPurpose.choices,
        default=ConsentPurpose.MARKETING_GENERAL,
    )
    status = models.CharField(
        _("status"),
        max_length=20,
        choices=ConsentStatus.choices,
        default=ConsentStatus.PENDING,
    )

    # Legal
    legal_basis = models.CharField(
        _("base legal"),
        max_length=30,
        choices=LegalBasis.choices,
        default=LegalBasis.CONSENT,
        help_text=_("Base legal LGPD para o tratamento de dados"),
    )

    # Source
    source = models.CharField(
        _("origem"),
        max_length=100,
        blank=True,
        help_text=_("Como o consentimento foi coletado (checkout, form, whatsapp)"),
    )
    policy_version = models.CharField(_("versão da política"), max_length=64, blank=True)
    disclosure_hash = models.CharField(_("hash do texto"), max_length=64, blank=True)
    evidence_hash = models.CharField(_("hash da evidência"), max_length=64, blank=True)
    locale = models.CharField(_("idioma"), max_length=16, default="pt-BR")
    proof_status = models.CharField(
        _("situação da prova"),
        max_length=24,
        choices=ConsentProofStatus.choices,
        default=ConsentProofStatus.LEGACY_UNVERIFIED,
    )
    last_event_ref = models.UUIDField(_("último evento"), null=True, blank=True, editable=False)
    ip_address = models.GenericIPAddressField(
        _("endereço IP"),
        blank=True,
        null=True,
        help_text=_("IP no momento do consentimento"),
    )

    # Timestamps
    consented_at = models.DateTimeField(
        _("consentido em"),
        null=True,
        blank=True,
        help_text=_("Data/hora do opt-in"),
    )
    revoked_at = models.DateTimeField(
        _("revogado em"),
        null=True,
        blank=True,
        help_text=_("Data/hora do opt-out"),
    )

    # Audit
    created_at = models.DateTimeField(_("criado em"), auto_now_add=True)
    updated_at = models.DateTimeField(_("atualizado em"), auto_now=True)

    class Meta:
        verbose_name = _("consentimento de comunicação")
        verbose_name_plural = _("consentimentos de comunicação")
        constraints = [
            models.UniqueConstraint(
                fields=["customer", "channel"],
                name="customers_unique_consent_per_channel",
            ),
        ]
        ordering = ["channel"]

    def __str__(self):
        return f"{self.customer.ref}: {self.channel} → {self.status}"

    @property
    def is_active(self) -> bool:
        """Whether communication is allowed on this channel."""
        return (
            self.status == ConsentStatus.OPTED_IN
            and self.proof_status == ConsentProofStatus.VERIFIED
        )


class CommunicationConsentEvent(models.Model):
    """Immutable evidence event; current consent is a rebuildable projection."""

    ref = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    customer = models.ForeignKey(
        "guestman.Customer",
        on_delete=models.SET_NULL,
        related_name="consent_events",
        verbose_name=_("cliente"),
        null=True,
        blank=True,
    )
    customer_ref_hash = models.CharField(_("identificador protegido"), max_length=64, db_index=True)
    channel = models.CharField(_("canal"), max_length=20, choices=ConsentChannel.choices)
    purpose = models.CharField(
        _("finalidade"),
        max_length=32,
        choices=ConsentPurpose.choices,
        default=ConsentPurpose.MARKETING_GENERAL,
    )
    event_type = models.CharField(_("evento"), max_length=24, choices=ConsentEventType.choices)
    resulting_status = models.CharField(_("estado resultante"), max_length=20, choices=ConsentStatus.choices)
    legal_basis = models.CharField(
        _("base legal"),
        max_length=30,
        choices=LegalBasis.choices,
        default=LegalBasis.CONSENT,
    )
    source = models.CharField(_("origem"), max_length=100, blank=True)
    disclosure_text = models.TextField(_("texto apresentado"), blank=True)
    disclosure_version = models.CharField(_("versão do texto"), max_length=64, blank=True)
    disclosure_hash = models.CharField(_("hash do texto"), max_length=64, blank=True)
    evidence_hash = models.CharField(_("hash da evidência"), max_length=64, unique=True)
    proof_status = models.CharField(
        _("situação da prova"),
        max_length=24,
        choices=ConsentProofStatus.choices,
        default=ConsentProofStatus.LEGACY_UNVERIFIED,
    )
    locale = models.CharField(_("idioma"), max_length=16, default="pt-BR")
    ip_address = models.GenericIPAddressField(_("endereço IP"), blank=True, null=True)
    actor_ref = models.CharField(_("responsável"), max_length=128, blank=True)
    occurred_at = models.DateTimeField(_("ocorrido em"))
    created_at = models.DateTimeField(_("registrado em"), auto_now_add=True)

    objects = models.Manager.from_queryset(_AppendOnlyConsentEventQuerySet)()

    class Meta:
        verbose_name = _("evento de consentimento")
        verbose_name_plural = _("eventos de consentimento")
        ordering = ["occurred_at", "pk"]
        indexes = [
            models.Index(fields=["customer", "channel", "purpose", "occurred_at"]),
        ]

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError(_("Eventos de consentimento são imutáveis."))
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError(_("Eventos de consentimento não podem ser apagados."))

    def __str__(self) -> str:  # pragma: no cover - admin/debug only
        return f"{self.channel}/{self.purpose}: {self.event_type} @ {self.occurred_at.isoformat()}"
