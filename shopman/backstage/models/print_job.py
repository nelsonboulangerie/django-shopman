"""Durable, auditable print delivery owned by Backstage.

``Terminal`` remains the identity/configuration of a physical station.  These
models own the document, its immutable bytes, delivery attempts and the relay
credential; Cashman never needs to know what an operational label is.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid

from django.conf import settings
from django.db import models


class PrintJob(models.Model):
    class Kind(models.TextChoices):
        PRODUCTION_WEIGHING = "production_weighing", "Pesagem cega"
        PRODUCTION_PREPARATION = "production_preparation", "Etiqueta de preparo"

    class Status(models.TextChoices):
        PREPARED = "prepared", "Preparada no navegador"
        QUEUED = "queued", "Na fila"
        LEASED = "leased", "Em envio"
        SPOOLED = "spooled", "Enviada à impressora"
        AWAITING_CONFIRMATION = "awaiting_confirmation", "Aguardando confirmação"
        CONFIRMED = "confirmed", "Confirmada"
        FAILED = "failed", "Falhou"
        UNCERTAIN = "uncertain", "Resultado incerto"
        CANCELLED = "cancelled", "Cancelada"
        EXPIRED = "expired", "Expirada"

    class Transport(models.TextChoices):
        RELAY = "relay", "Relay"
        BROWSER = "browser", "Navegador"

    class Confirmation(models.TextChoices):
        CONFIRMED = "confirmed", "Impressão confirmada"
        INCOMPLETE = "incomplete", "Impressão incompleta"
        NOT_PRINTED = "not_printed", "Não imprimiu"

    ref = models.UUIDField("referência", default=uuid.uuid4, unique=True, editable=False)
    kind = models.CharField("tipo", max_length=40, choices=Kind.choices)
    transport = models.CharField("transporte", max_length=12, choices=Transport.choices)
    status = models.CharField("status", max_length=24, choices=Status.choices, default=Status.QUEUED)
    target_terminal = models.ForeignKey(
        "cashman.Terminal",
        on_delete=models.PROTECT,
        related_name="backstage_print_jobs",
        verbose_name="terminal de destino",
        null=True,
        blank=True,
    )
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="backstage_print_jobs_requested",
        verbose_name="solicitado por",
    )
    requested_by_ref = models.CharField("identificação do solicitante", max_length=150)
    requested_station_ref = models.CharField("estação solicitante", max_length=80, blank=True, default="")
    source_revision = models.CharField("revisão de origem", max_length=256)
    document = models.JSONField("documento congelado")
    document_sha256 = models.CharField("hash do documento", max_length=64)
    renderer_version = models.PositiveSmallIntegerField("versão do renderizador", default=1)
    payload = models.BinaryField("bytes ESC/POS")
    payload_sha256 = models.CharField("hash dos bytes", max_length=64)
    payload_size = models.PositiveIntegerField("tamanho dos bytes")
    label_count = models.PositiveSmallIntegerField("quantidade de etiquetas")
    series_ref = models.UUIDField("série", default=uuid.uuid4, editable=False)
    copy_number = models.PositiveSmallIntegerField("via", default=1)
    reprint_of = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="reprints",
        verbose_name="reimpressão de",
    )
    confirmation = models.CharField(
        "resultado confirmado",
        max_length=20,
        choices=Confirmation.choices,
        blank=True,
        default="",
    )
    confirmation_detail = models.CharField("detalhe da confirmação", max_length=500, blank=True, default="")
    confirmed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="backstage_print_jobs_confirmed",
        verbose_name="confirmado por",
    )
    confirmed_at = models.DateTimeField("confirmado em", null=True, blank=True)
    confirmed_by_ref = models.CharField("identificação de quem confirmou", max_length=150, blank=True, default="")
    expires_at = models.DateTimeField("expira em", db_index=True)
    created_at = models.DateTimeField("criado em", auto_now_add=True)
    updated_at = models.DateTimeField("atualizado em", auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "trabalho de impressão"
        verbose_name_plural = "trabalhos de impressão"
        constraints = [
            models.UniqueConstraint(fields=("series_ref", "copy_number"), name="backstage_printjob_unique_copy"),
            models.CheckConstraint(condition=models.Q(copy_number__gte=1), name="backstage_printjob_copy_positive"),
            models.CheckConstraint(condition=models.Q(label_count__gte=1), name="backstage_printjob_labels_positive"),
        ]
        indexes = [
            models.Index(fields=("target_terminal", "status", "created_at"), name="backstage_pj_target_status_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.ref} · {self.get_status_display()}"


class PrintAgentCredential(models.Model):
    """Revocable machine credential bound to exactly one terminal.

    The bearer is ``<ref>.<secret>``.  Only an HMAC digest and a short hint are
    persisted; neither projections nor job responses can recover the secret.
    """

    ref = models.UUIDField("referência", default=uuid.uuid4, unique=True, editable=False)
    terminal = models.ForeignKey(
        "cashman.Terminal",
        on_delete=models.PROTECT,
        related_name="print_agent_credentials",
        verbose_name="terminal",
    )
    label = models.CharField("rótulo", max_length=120, blank=True, default="")
    token_digest = models.CharField("digest do token", max_length=64, editable=False)
    token_hint = models.CharField("final do token", max_length=8, editable=False)
    is_active = models.BooleanField("ativa", default=True)
    last_seen_at = models.DateTimeField("vista por último em", null=True, blank=True)
    last_build = models.CharField("último build", max_length=120, blank=True, default="")
    last_remote_addr = models.GenericIPAddressField("último IP", null=True, blank=True)
    created_at = models.DateTimeField("criada em", auto_now_add=True)
    rotated_at = models.DateTimeField("rotacionada em", auto_now_add=True)
    revoked_at = models.DateTimeField("revogada em", null=True, blank=True)

    class Meta:
        ordering = ["terminal__ref", "label", "pk"]
        verbose_name = "credencial do agente de impressão"
        verbose_name_plural = "credenciais dos agentes de impressão"

    @staticmethod
    def _digest(secret: str) -> str:
        key = str(settings.SECRET_KEY).encode("utf-8")
        return hmac.new(key, secret.encode("utf-8"), hashlib.sha256).hexdigest()

    @classmethod
    def issue(cls, *, terminal, label: str = "") -> tuple[PrintAgentCredential, str]:
        secret = secrets.token_urlsafe(32)
        credential = cls.objects.create(
            terminal=terminal,
            label=str(label or "").strip(),
            token_digest=cls._digest(secret),
            token_hint=secret[-6:],
        )
        return credential, f"{credential.ref}.{secret}"

    def rotate(self) -> str:
        from django.utils import timezone

        secret = secrets.token_urlsafe(32)
        self.token_digest = self._digest(secret)
        self.token_hint = secret[-6:]
        self.is_active = True
        self.revoked_at = None
        self.rotated_at = timezone.now()
        self.save(update_fields=("token_digest", "token_hint", "is_active", "revoked_at", "rotated_at"))
        return f"{self.ref}.{secret}"

    @classmethod
    def authenticate(cls, bearer: str) -> PrintAgentCredential | None:
        try:
            raw_ref, secret = str(bearer or "").strip().split(".", 1)
            ref = uuid.UUID(raw_ref)
        except (ValueError, AttributeError):
            return None
        credential = cls.objects.select_related("terminal").filter(
            ref=ref,
            is_active=True,
            terminal__is_active=True,
        ).first()
        if credential is None or not hmac.compare_digest(credential.token_digest, cls._digest(secret)):
            return None
        return credential

    def __str__(self) -> str:
        return self.label or f"{self.terminal.ref} · …{self.token_hint}"


class PrintAttempt(models.Model):
    class Status(models.TextChoices):
        LEASED = "leased", "Em envio"
        SPOOLED = "spooled", "Enviada à impressora"
        FAILED = "failed", "Falhou"
        UNCERTAIN = "uncertain", "Resultado incerto"
        EXPIRED = "expired", "Lease expirado"
        BROWSER_OPENED = "browser_opened", "Diálogo do navegador aberto"
        BROWSER_UNAVAILABLE = "browser_unavailable", "Diálogo do navegador indisponível"

    job = models.ForeignKey(PrintJob, on_delete=models.PROTECT, related_name="attempts", verbose_name="trabalho")
    sequence = models.PositiveSmallIntegerField("tentativa")
    status = models.CharField("status", max_length=24, choices=Status.choices, default=Status.LEASED)
    credential = models.ForeignKey(
        PrintAgentCredential,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="attempts",
        verbose_name="credencial",
    )
    lease_token_digest = models.CharField("digest do lease", max_length=64, blank=True, default="", editable=False)
    lease_expires_at = models.DateTimeField("lease expira em", null=True, blank=True)
    claimed_at = models.DateTimeField("capturada em", auto_now_add=True)
    acknowledged_at = models.DateTimeField("respondida em", null=True, blank=True)
    spooler_job_id = models.CharField("job do spooler", max_length=160, blank=True, default="")
    agent_version = models.CharField("versão do agente", max_length=80, blank=True, default="")
    agent_build = models.CharField("build do agente", max_length=120, blank=True, default="")
    queue_name = models.CharField("fila observada", max_length=160, blank=True, default="")
    health = models.CharField("saúde observada", max_length=40, blank=True, default="")
    detail = models.CharField("detalhe", max_length=500, blank=True, default="")
    ack_digest = models.CharField("digest do ACK", max_length=64, blank=True, default="", editable=False)

    class Meta:
        ordering = ["job_id", "sequence"]
        verbose_name = "tentativa de impressão"
        verbose_name_plural = "tentativas de impressão"
        constraints = [
            models.UniqueConstraint(fields=("job", "sequence"), name="backstage_printattempt_unique_sequence"),
            models.CheckConstraint(condition=models.Q(sequence__gte=1), name="backstage_printattempt_sequence_positive"),
        ]

    def __str__(self) -> str:
        return f"{self.job.ref} · tentativa {self.sequence}"
