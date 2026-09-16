"""Recibos duráveis sem PII em claro para direitos de dados da conta."""

from __future__ import annotations

import uuid
from datetime import timedelta

from django.core.validators import RegexValidator
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

PRIVACY_RECEIPT_RETENTION = timedelta(days=365 * 5)


def privacy_receipt_retention_until():
    """Prazo padrão serializável; o serviço ajusta o prazo ao encerrar."""

    return timezone.now() + PRIVACY_RECEIPT_RETENTION


class PrivacyRequestOperation(models.TextChoices):
    EXPORT = "export", _("exportação")
    DELETION = "deletion", _("exclusão")


class PrivacyRequestState(models.TextChoices):
    IN_PROGRESS = "in_progress", _("em andamento")
    COMPLETED = "completed", _("concluído")
    FAILED = "failed", _("falhou")


_HMAC_DIGEST_VALIDATOR = RegexValidator(
    regex=r"\A[0-9a-f]{64}\Z",
    message=_("Informe um digest HMAC hexadecimal de 64 caracteres."),
)


class PrivacyRequestReceipt(models.Model):
    """Evidência segura de uma solicitação de exportação ou exclusão.

    O recibo não referencia o cadastro e não guarda identificadores, chaves de
    idempotência, conteúdo exportado ou exceções em claro. Os três digests são
    pseudônimos HMAC versionados; resultados e falhas ficam limitados a
    contagens e códigos.
    """

    ref = models.UUIDField(_("referência"), default=uuid.uuid4, unique=True, editable=False)
    operation = models.CharField(
        _("operação"),
        max_length=16,
        choices=PrivacyRequestOperation.choices,
    )
    state = models.CharField(
        _("situação"),
        max_length=16,
        choices=PrivacyRequestState.choices,
        default=PrivacyRequestState.IN_PROGRESS,
    )
    key_version = models.PositiveIntegerField(
        _("versão da chave HMAC"),
        default=1,
        help_text=_("Versão opaca usada para validar o recibo após rotação de chave."),
    )
    subject_digest = models.CharField(
        _("digest do titular"),
        max_length=64,
        validators=[_HMAC_DIGEST_VALIDATOR],
    )
    idempotency_digest = models.CharField(
        _("digest da idempotência"),
        max_length=64,
        validators=[_HMAC_DIGEST_VALIDATOR],
    )
    request_digest = models.CharField(
        _("digest da solicitação"),
        max_length=64,
        validators=[_HMAC_DIGEST_VALIDATOR],
    )
    authorization_method = models.CharField(
        _("método de autorização"),
        max_length=32,
        help_text=_("Código estável do método, sem credenciais ou identificadores."),
    )
    authorized_at = models.DateTimeField(_("autorizado em"))
    failure_stage = models.CharField(
        _("etapa da falha"),
        max_length=48,
        blank=True,
        help_text=_("Código estável da etapa; nunca uma mensagem de exceção."),
    )
    failure_code = models.CharField(
        _("código da falha"),
        max_length=64,
        blank=True,
        help_text=_("Código estável e seguro para exposição; nunca a exceção em claro."),
    )
    outcome_counts = models.JSONField(
        _("contagens do resultado"),
        default=dict,
        blank=True,
        help_text=_("Somente contagens agregadas, sem conteúdo ou identificadores."),
    )
    attempt_count = models.PositiveIntegerField(_("tentativas"), default=1)
    started_at = models.DateTimeField(_("iniciado em"), default=timezone.now)
    completed_at = models.DateTimeField(_("concluído em"), null=True, blank=True)
    updated_at = models.DateTimeField(_("atualizado em"), auto_now=True)
    retention_until = models.DateTimeField(
        _("reter até"),
        default=privacy_receipt_retention_until,
    )

    class Meta:
        ordering = ["-started_at", "-pk"]
        verbose_name = _("recibo de solicitação de privacidade")
        verbose_name_plural = _("recibos de solicitações de privacidade")
        constraints = [
            models.UniqueConstraint(
                fields=["operation", "idempotency_digest"],
                name="shop_privacy_receipt_operation_idem_uq",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(
                        state=PrivacyRequestState.IN_PROGRESS,
                        completed_at__isnull=True,
                    )
                    | models.Q(
                        state__in=(
                            PrivacyRequestState.COMPLETED,
                            PrivacyRequestState.FAILED,
                        ),
                        completed_at__isnull=False,
                    )
                ),
                name="shop_privacy_receipt_terminal_completed_ck",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(subject_digest__regex=r"^[0-9a-f]{64}$")
                    & models.Q(idempotency_digest__regex=r"^[0-9a-f]{64}$")
                    & models.Q(request_digest__regex=r"^[0-9a-f]{64}$")
                ),
                name="shop_privacy_receipt_hmac_digests_ck",
            ),
            models.CheckConstraint(
                condition=models.Q(attempt_count__gte=1),
                name="shop_privacy_receipt_attempt_count_ck",
            ),
            models.CheckConstraint(
                condition=models.Q(key_version__gte=1),
                name="shop_privacy_receipt_key_version_ck",
            ),
        ]
        indexes = [
            models.Index(
                fields=["subject_digest", "operation"],
                name="shop_privacy_subject_op_idx",
            ),
            models.Index(
                fields=["state", "retention_until"],
                name="shop_privacy_state_ret_idx",
            ),
        ]

    def __str__(self) -> str:  # pragma: no cover - Admin/debug only
        return f"{self.get_operation_display()} · {self.get_state_display()} · {self.ref}"
