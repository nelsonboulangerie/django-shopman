"""Alertas pessoais persistentes, vinculados a uma condição de origem.

``is_read``/``read_at`` continuam durante a migração dos clientes antigos. A
verdade nova é ``lifecycle``: ver um alerta não prova que a condição acabou.
Cada mudança de estado gera um ``UserNotificationEvent`` append-only.
"""

from __future__ import annotations

from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone

NOTIFICATION_RETENTION = timedelta(days=365 * 5)


def notification_retention_until():
    """Default serializável para evidência operacional do alerta."""

    return timezone.now() + NOTIFICATION_RETENTION


class NotificationCategory(models.TextChoices):
    CAMPAIGN = "campaign", "campanha"
    PRODUCTION = "production", "produção"
    ORDER = "order", "pedidos"
    SYSTEM = "system", "sistema"


class NotificationSeverity(models.TextChoices):
    INFORMATION = "information", "informação"
    ACTION_REQUIRED = "action_required", "ação necessária"
    WARNING = "warning", "atenção"
    CRITICAL = "critical", "crítico"


class NotificationLifecycle(models.TextChoices):
    UNSEEN = "unseen", "não visto"
    SEEN = "seen", "visto"
    ACKNOWLEDGED = "acknowledged", "assumido"
    RESOLVED = "resolved", "resolvido"
    EXPIRED = "expired", "expirado"


ACTIVE_NOTIFICATION_STATES = (
    NotificationLifecycle.UNSEEN,
    NotificationLifecycle.SEEN,
    NotificationLifecycle.ACKNOWLEDGED,
)
CLOSED_NOTIFICATION_STATES = (
    NotificationLifecycle.RESOLVED,
    NotificationLifecycle.EXPIRED,
)


class NotificationEventType(models.TextChoices):
    CREATED = "created", "criado"
    DEDUPED = "deduped", "duplicado evitado"
    SEEN = "seen", "visto"
    ACKNOWLEDGED = "acknowledged", "assumido"
    REFRESHED = "refreshed", "origem atualizada"
    ACTION_CHOSEN = "action_chosen", "ação escolhida"
    ACTION_SUCCEEDED = "action_succeeded", "ação concluída"
    ACTION_FAILED = "action_failed", "ação falhou"
    RESOLVED = "resolved", "resolvido"
    EXPIRED = "expired", "expirado"


class UserNotification(models.Model):
    """Uma representação pessoal de uma condição operacional persistente."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
        verbose_name="usuário",
    )
    category = models.CharField(
        "categoria",
        max_length=32,
        choices=NotificationCategory.choices,
        default=NotificationCategory.SYSTEM,
    )
    title = models.CharField("título", max_length=200)
    message = models.TextField("mensagem", blank=True)
    action_url = models.CharField(
        "link",
        max_length=500,
        blank=True,
        help_text="Compatibilidade; Actions canônicas nunca executam este valor.",
    )
    action_data = models.JSONField(
        "dados da ação",
        default=dict,
        blank=True,
        help_text="Compatibilidade; somente campos allowlisted são projetados.",
    )
    is_actionable = models.BooleanField(
        "acionável",
        default=False,
        help_text="Compatibilidade; a Action real é resolvida no servidor.",
    )

    # Dual projection legado. ``read`` significa somente ``seen``.
    is_read = models.BooleanField("lida", default=False)
    read_at = models.DateTimeField("lida em", null=True, blank=True)

    lifecycle = models.CharField(
        "ciclo de vida",
        max_length=16,
        choices=NotificationLifecycle.choices,
        default=NotificationLifecycle.UNSEEN,
    )
    severity = models.CharField(
        "severidade",
        max_length=24,
        choices=NotificationSeverity.choices,
        default=NotificationSeverity.INFORMATION,
    )
    source_condition = models.CharField("condição de origem", max_length=64, blank=True)
    source_ref = models.CharField("referência de origem", max_length=120, blank=True)
    source_version = models.PositiveIntegerField("versão da origem", default=1)
    group_key = models.CharField("grupo de reconciliação", max_length=255, blank=True, db_index=True)
    dedupe_key = models.CharField("chave de deduplicação", max_length=320, blank=True)
    owner_role = models.CharField("função responsável", max_length=32, blank=True)
    escalation_role = models.CharField("função de escalação", max_length=32, blank=True)
    escalates_at = models.DateTimeField("escala em", null=True, blank=True)
    expires_at = models.DateTimeField("expira em", null=True, blank=True)
    acknowledged_at = models.DateTimeField("assumida em", null=True, blank=True)
    resolved_at = models.DateTimeField("resolvida em", null=True, blank=True)
    lifecycle_updated_at = models.DateTimeField("estado atualizado em", default=timezone.now)
    version = models.PositiveIntegerField("versão", default=1, editable=False)

    created_at = models.DateTimeField(auto_now_add=True)
    retention_until = models.DateTimeField(default=notification_retention_until)

    class Meta:
        ordering = ["-created_at", "-pk"]
        verbose_name = "notificação"
        verbose_name_plural = "notificações"
        indexes = [
            models.Index(fields=["user", "is_read", "-created_at"]),
            models.Index(fields=["user", "lifecycle", "severity", "-created_at"]),
            models.Index(fields=["source_condition", "source_ref", "source_version"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["dedupe_key"],
                condition=~Q(dedupe_key=""),
                name="shop_user_notification_dedupe_key_uq",
            ),
        ]

    def __str__(self) -> str:  # pragma: no cover - admin/debug only
        return f"[{self.lifecycle}] {self.title}"

    @property
    def is_active(self) -> bool:
        return self.lifecycle in ACTIVE_NOTIFICATION_STATES

    def mark_read(self) -> None:
        """Compatibilidade: leitura vira ``seen`` e nunca ``resolved``."""

        if self.pk is None:
            raise ValueError("A notificação precisa estar salva antes de ser marcada.")
        from shopman.shop.services.user_notifications import mark_seen

        refreshed = mark_seen(notification_id=self.pk, actor=self.user)
        for field in (
            "is_read",
            "read_at",
            "lifecycle",
            "lifecycle_updated_at",
            "version",
        ):
            setattr(self, field, getattr(refreshed, field))


class _AppendOnlyNotificationEventQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise ValidationError("Eventos de alerta são imutáveis.")

    def delete(self):
        raise ValidationError("Eventos de alerta não podem ser apagados diretamente.")


class UserNotificationEvent(models.Model):
    """Evidência append-only do caminho alerta → ação → resolução."""

    notification = models.ForeignKey(
        UserNotification,
        on_delete=models.CASCADE,
        related_name="lifecycle_events",
    )
    command = models.ForeignKey(
        "shop.MarketingCommandReceipt",
        on_delete=models.PROTECT,
        related_name="notification_lifecycle_events",
        null=True,
        blank=True,
    )
    event_type = models.CharField(max_length=24, choices=NotificationEventType.choices)
    from_state = models.CharField(max_length=16, choices=NotificationLifecycle.choices)
    to_state = models.CharField(max_length=16, choices=NotificationLifecycle.choices)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="notification_lifecycle_events",
        null=True,
        blank=True,
    )
    actor_ref = models.CharField(max_length=64, blank=True, db_index=True)
    action_code = models.CharField(max_length=40, blank=True)
    outcome_code = models.CharField(max_length=64, blank=True)
    source_condition = models.CharField(max_length=64, blank=True)
    source_ref = models.CharField(max_length=120, blank=True)
    source_version = models.PositiveIntegerField(default=1)
    facts = models.JSONField(default=dict, blank=True)
    occurred_at = models.DateTimeField(default=timezone.now)
    retention_until = models.DateTimeField(default=notification_retention_until)

    objects = models.Manager.from_queryset(_AppendOnlyNotificationEventQuerySet)()

    class Meta:
        ordering = ["-occurred_at", "-pk"]
        indexes = [
            models.Index(fields=["notification", "occurred_at"]),
            models.Index(fields=["event_type", "occurred_at"]),
            models.Index(fields=["source_condition", "source_ref", "occurred_at"]),
        ]

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError("Eventos de alerta são imutáveis.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Eventos de alerta não podem ser apagados diretamente.")
