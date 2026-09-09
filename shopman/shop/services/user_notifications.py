"""Lifecycle, dedupe e reconciliação de alertas pessoais do operador."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime

from django.db import IntegrityError, transaction
from django.utils import timezone

from shopman.shop.models import (
    Announcement,
    AnnouncementStatus,
    MarketingCommandReceipt,
    NotificationEventType,
    NotificationLifecycle,
    NotificationSeverity,
    UserNotification,
    UserNotificationEvent,
)
from shopman.shop.models.user_notification import ACTIVE_NOTIFICATION_STATES

logger = logging.getLogger(__name__)

ANNOUNCEMENT_REVIEW = "announcement_review"
OWNER_PRODUCT = "product"
ESCALATION_OPS = "ops"


@dataclass(frozen=True, slots=True)
class AlertCreation:
    notification: UserNotification
    created: bool


def create_condition_alert(
    *,
    user,
    category: str,
    title: str,
    message: str,
    source_condition: str,
    source_ref: str,
    source_version: int,
    action_data: dict | None = None,
    severity: str = NotificationSeverity.ACTION_REQUIRED,
    owner_role: str,
    escalation_role: str = "",
    escalates_at: datetime | None = None,
    expires_at: datetime | None = None,
) -> AlertCreation:
    """Cria uma representação por owner e evita duplicar a mesma condição."""

    if not getattr(user, "pk", None):
        raise ValueError("O alerta exige um owner persistido.")
    source_condition = str(source_condition or "").strip()
    source_ref = str(source_ref or "").strip()
    if not source_condition or not source_ref or int(source_version) < 1:
        raise ValueError("Condição, referência e versão de origem são obrigatórias.")

    group_key = _group_key(source_condition, source_ref, int(source_version))
    dedupe_key = _dedupe_key(group_key, int(user.pk))
    defaults = {
        "user": user,
        "category": category,
        "title": title,
        "message": message,
        # O legado recebe só o deep-link relativo conhecido. A projeção v2 não lê
        # este campo; resolve a Action novamente a partir da condição.
        "action_url": _known_deep_link(source_condition, source_ref),
        "action_data": dict(action_data or {}),
        "is_actionable": severity != NotificationSeverity.INFORMATION,
        "lifecycle": NotificationLifecycle.UNSEEN,
        "severity": severity,
        "source_condition": source_condition,
        "source_ref": source_ref,
        "source_version": int(source_version),
        "group_key": group_key,
        "owner_role": owner_role,
        "escalation_role": escalation_role,
        "escalates_at": escalates_at,
        "expires_at": expires_at,
    }

    try:
        with transaction.atomic():
            notification, created = UserNotification.objects.get_or_create(
                dedupe_key=dedupe_key,
                defaults=defaults,
            )
            _append_event(
                notification,
                NotificationEventType.CREATED if created else NotificationEventType.DEDUPED,
                from_state=notification.lifecycle,
                to_state=notification.lifecycle,
                outcome_code="created" if created else "same_condition_same_owner",
            )
            if created:
                _push_after_commit(notification)
    except IntegrityError:
        # Compatibilidade com bancos que reportam a corrida fora do savepoint de
        # get_or_create. A unique key continua sendo a autoridade.
        notification = UserNotification.objects.get(dedupe_key=dedupe_key)
        with transaction.atomic():
            _append_event(
                notification,
                NotificationEventType.DEDUPED,
                from_state=notification.lifecycle,
                to_state=notification.lifecycle,
                outcome_code="concurrent_create",
            )
        created = False

    logger.info(
        "operator_notification.%s condition=%s owner_role=%s",
        "created" if created else "deduped",
        source_condition,
        owner_role,
    )
    return AlertCreation(notification=notification, created=created)


def mark_seen(*, notification_id: int, actor) -> UserNotification:
    """Registra a primeira visualização sem encerrar a condição."""

    with transaction.atomic():
        notification = _owned_for_update(notification_id, actor)
        if notification.lifecycle != NotificationLifecycle.UNSEEN:
            return notification
        now = timezone.now()
        previous = notification.lifecycle
        notification.lifecycle = NotificationLifecycle.SEEN
        notification.lifecycle_updated_at = now
        notification.is_read = True
        notification.read_at = notification.read_at or now
        notification.version += 1
        notification.save(
            update_fields=[
                "lifecycle",
                "lifecycle_updated_at",
                "is_read",
                "read_at",
                "version",
            ]
        )
        _append_event(
            notification,
            NotificationEventType.SEEN,
            from_state=previous,
            to_state=notification.lifecycle,
            actor=actor,
            occurred_at=now,
        )
        _push_after_commit(notification)
        return notification


def acknowledge(*, notification_id: int, actor) -> UserNotification:
    """Assume responsabilidade; ainda não significa que a origem foi resolvida."""

    with transaction.atomic():
        notification = _owned_for_update(notification_id, actor)
        if notification.lifecycle not in {
            NotificationLifecycle.UNSEEN,
            NotificationLifecycle.SEEN,
        }:
            return notification
        now = timezone.now()
        previous = notification.lifecycle
        notification.lifecycle = NotificationLifecycle.ACKNOWLEDGED
        notification.lifecycle_updated_at = now
        notification.acknowledged_at = notification.acknowledged_at or now
        notification.is_read = True
        notification.read_at = notification.read_at or now
        notification.version += 1
        notification.save(
            update_fields=[
                "lifecycle",
                "lifecycle_updated_at",
                "acknowledged_at",
                "is_read",
                "read_at",
                "version",
            ]
        )
        _append_event(
            notification,
            NotificationEventType.ACKNOWLEDGED,
            from_state=previous,
            to_state=notification.lifecycle,
            actor=actor,
            occurred_at=now,
        )
        _push_after_commit(notification)
        return notification


def mark_seen_many(*, notification_ids, actor) -> int:
    """Marca como vistos apenas IDs unseen do owner, em custo constante."""

    actor_id = getattr(actor, "pk", None)
    if not actor_id:
        raise UserNotification.DoesNotExist
    ids = tuple(
        sorted(
            {
                int(raw)
                for raw in notification_ids
                if isinstance(raw, int) and not isinstance(raw, bool) and raw > 0
            }
        )
    )
    if not ids:
        return 0
    now = timezone.now()
    with transaction.atomic():
        notifications = list(
            UserNotification.objects.select_for_update()
            .filter(
                pk__in=ids,
                user_id=actor_id,
                lifecycle=NotificationLifecycle.UNSEEN,
            )
            .order_by("pk")
        )
        events = []
        for notification in notifications:
            notification.lifecycle = NotificationLifecycle.SEEN
            notification.lifecycle_updated_at = now
            notification.is_read = True
            notification.read_at = notification.read_at or now
            notification.version += 1
            events.append(
                _event_record(
                    notification,
                    NotificationEventType.SEEN,
                    from_state=NotificationLifecycle.UNSEEN,
                    to_state=NotificationLifecycle.SEEN,
                    actor=actor,
                    outcome_code="visible_in_alert_panel",
                    occurred_at=now,
                )
            )
        if notifications:
            UserNotification.objects.bulk_update(
                notifications,
                fields=[
                    "lifecycle",
                    "lifecycle_updated_at",
                    "is_read",
                    "read_at",
                    "version",
                ],
            )
            UserNotificationEvent.objects.bulk_create(events)
            _push_batch_after_commit(user_id=actor_id)
        return len(notifications)


def record_action(
    *,
    notification_id: int,
    actor,
    action_code: str,
    outcome_code: str = "",
    succeeded: bool | None = None,
) -> UserNotification:
    """Liga a escolha e seu resultado ao alerta, sem esconder falhas."""

    with transaction.atomic():
        notification = _owned_for_update(notification_id, actor)
        if succeeded is None:
            event_type = NotificationEventType.ACTION_CHOSEN
        elif succeeded:
            event_type = NotificationEventType.ACTION_SUCCEEDED
        else:
            event_type = NotificationEventType.ACTION_FAILED
        _append_event(
            notification,
            event_type,
            from_state=notification.lifecycle,
            to_state=notification.lifecycle,
            actor=actor,
            action_code=str(action_code or "")[:40],
            outcome_code=str(outcome_code or "")[:64],
        )
        return notification


def reconcile_user_notifications(*, user) -> int:
    """Compara alertas ativos do owner com fontes canônicas em lote."""

    active = list(
        UserNotification.objects.filter(
            user=user,
            lifecycle__in=ACTIVE_NOTIFICATION_STATES,
        ).values("source_condition", "source_ref", "source_version")
    )
    if not active:
        return 0

    review_refs = {row["source_ref"] for row in active if row["source_condition"] == ANNOUNCEMENT_REVIEW}
    announcement_ids = {
        parsed for source_ref in review_refs if (parsed := _resource_id(source_ref, "announcement")) is not None
    }
    announcements = {
        f"announcement:{announcement.pk}": announcement
        for announcement in Announcement.objects.filter(pk__in=announcement_ids).select_related("rule")
    }

    changed = 0
    seen_sources: set[tuple[str, str]] = set()
    for row in active:
        key = (row["source_condition"], row["source_ref"])
        if key in seen_sources:
            continue
        seen_sources.add(key)
        # Registros criados por clientes v1 durante a janela de dual-write não
        # ganham uma condição por adivinhação. A migração expira os legados já
        # existentes; novos produtores devem adotar ``create_condition_alert``.
        if not row["source_condition"]:
            continue
        if row["source_condition"] != ANNOUNCEMENT_REVIEW:
            changed += reconcile_condition(
                source_condition=row["source_condition"],
                source_ref=row["source_ref"],
                state=NotificationLifecycle.EXPIRED,
                outcome_code="unsupported_source_condition",
            )
            continue
        announcement = announcements.get(row["source_ref"])
        if announcement is None:
            changed += reconcile_condition(
                source_condition=ANNOUNCEMENT_REVIEW,
                source_ref=row["source_ref"],
                state=NotificationLifecycle.EXPIRED,
                outcome_code="source_missing",
            )
            continue
        changed += reconcile_announcement_review(announcement)
    return changed


def reconcile_announcement_review(announcement: Announcement) -> int:
    """Mantém todas as representações de uma revisão alinhadas ao anúncio."""

    source_ref = f"announcement:{announcement.pk}"
    if announcement.status == AnnouncementStatus.PENDING_REVIEW and not announcement.is_expired():
        return _refresh_active_review_alerts(announcement, source_ref=source_ref)

    state = (
        NotificationLifecycle.EXPIRED
        if announcement.status == AnnouncementStatus.EXPIRED or announcement.is_expired()
        else NotificationLifecycle.RESOLVED
    )
    return reconcile_condition(
        source_condition=ANNOUNCEMENT_REVIEW,
        source_ref=source_ref,
        state=state,
        outcome_code=f"announcement_{announcement.status}",
    )


def reconcile_condition(
    *,
    source_condition: str,
    source_ref: str,
    state: str,
    outcome_code: str,
) -> int:
    """Fecha todos os siblings ativos da condição na mesma transação."""

    if state not in {NotificationLifecycle.RESOLVED, NotificationLifecycle.EXPIRED}:
        raise ValueError("Reconciliação só pode fechar como resolved ou expired.")
    now = timezone.now()
    with transaction.atomic():
        siblings = list(
            UserNotification.objects.select_for_update()
            .filter(
                source_condition=source_condition,
                source_ref=source_ref,
                lifecycle__in=ACTIVE_NOTIFICATION_STATES,
            )
            .order_by("pk")
        )
        events = []
        command = _source_command(
            source_condition=source_condition,
            source_ref=source_ref,
            source_versions={notification.source_version for notification in siblings},
        )
        for notification in siblings:
            previous = notification.lifecycle
            notification.lifecycle = state
            notification.lifecycle_updated_at = now
            notification.resolved_at = now
            # Dual projection: o endpoint legado não deve ressuscitar condição fechada.
            # ``read_at`` permanece a evidência honesta da visualização real.
            notification.is_read = True
            notification.is_actionable = False
            notification.version += 1
            events.append(
                _event_record(
                    notification,
                    NotificationEventType.EXPIRED
                    if state == NotificationLifecycle.EXPIRED
                    else NotificationEventType.RESOLVED,
                    from_state=previous,
                    to_state=state,
                    outcome_code=outcome_code,
                    command=command,
                    occurred_at=now,
                )
            )
        if siblings:
            UserNotification.objects.bulk_update(
                siblings,
                fields=[
                    "lifecycle",
                    "lifecycle_updated_at",
                    "resolved_at",
                    "is_read",
                    "is_actionable",
                    "version",
                ],
            )
            UserNotificationEvent.objects.bulk_create(events)
        for notification in siblings:
            _push_after_commit(notification)
    if siblings:
        logger.info(
            "operator_notification.reconciled condition=%s state=%s siblings=%s outcome=%s",
            source_condition,
            state,
            len(siblings),
            outcome_code,
        )
    return len(siblings)


def push_user_notification(notification: UserNotification) -> None:
    """Emite somente invalidação mínima; a verdade volta pelo fetch canônico."""

    payload = {"id": notification.pk, "category": notification.category}
    try:
        from django_eventstream import send_event

        send_event(f"user-{notification.user_id}", "user-notification", payload)
    except ImportError:
        return
    except Exception:
        logger.warning(
            "operator_notification.user_push_failed user=%s",
            notification.user_id,
            exc_info=True,
        )


def _refresh_active_review_alerts(announcement: Announcement, *, source_ref: str) -> int:
    now = timezone.now()
    with transaction.atomic():
        siblings = list(
            UserNotification.objects.select_for_update()
            .filter(
                source_condition=ANNOUNCEMENT_REVIEW,
                source_ref=source_ref,
                lifecycle__in=ACTIVE_NOTIFICATION_STATES,
            )
            .exclude(source_version=announcement.version)
            .order_by("pk")
        )
        events = []
        for notification in siblings:
            previous_version = notification.source_version
            group_key = _group_key(ANNOUNCEMENT_REVIEW, source_ref, announcement.version)
            notification.source_version = announcement.version
            notification.group_key = group_key
            notification.dedupe_key = _dedupe_key(group_key, notification.user_id)
            notification.expires_at = announcement.expires_at
            notification.message = _review_message(announcement)
            notification.lifecycle_updated_at = now
            notification.version += 1
            events.append(
                _event_record(
                    notification,
                    NotificationEventType.REFRESHED,
                    from_state=notification.lifecycle,
                    to_state=notification.lifecycle,
                    outcome_code="source_version_changed",
                    facts={
                        "previous_source_version": previous_version,
                        "resulting_source_version": announcement.version,
                    },
                    occurred_at=now,
                )
            )
        if siblings:
            UserNotification.objects.bulk_update(
                siblings,
                fields=[
                    "source_version",
                    "group_key",
                    "dedupe_key",
                    "expires_at",
                    "message",
                    "lifecycle_updated_at",
                    "version",
                ],
            )
            UserNotificationEvent.objects.bulk_create(events)
        for notification in siblings:
            _push_after_commit(notification)
    return len(siblings)


def _owned_for_update(notification_id: int, actor) -> UserNotification:
    actor_id = getattr(actor, "pk", None)
    if not actor_id:
        raise UserNotification.DoesNotExist
    return UserNotification.objects.select_for_update().get(
        pk=notification_id,
        user_id=actor_id,
    )


def _append_event(
    notification: UserNotification,
    event_type: str,
    *,
    from_state: str,
    to_state: str,
    actor=None,
    command=None,
    action_code: str = "",
    outcome_code: str = "",
    facts: dict | None = None,
    occurred_at: datetime | None = None,
) -> UserNotificationEvent:
    event = _event_record(
        notification,
        event_type,
        from_state=from_state,
        to_state=to_state,
        actor=actor,
        command=command,
        action_code=action_code,
        outcome_code=outcome_code,
        facts=facts,
        occurred_at=occurred_at,
    )
    event.save()
    return event


def _event_record(
    notification: UserNotification,
    event_type: str,
    *,
    from_state: str,
    to_state: str,
    actor=None,
    command=None,
    action_code: str = "",
    outcome_code: str = "",
    facts: dict | None = None,
    occurred_at: datetime | None = None,
) -> UserNotificationEvent:
    return UserNotificationEvent(
        notification=notification,
        event_type=event_type,
        from_state=from_state,
        to_state=to_state,
        actor=actor if getattr(actor, "pk", None) else None,
        command=command,
        actor_ref=f"user:{actor.pk}" if getattr(actor, "pk", None) else "system",
        action_code=action_code,
        outcome_code=outcome_code,
        source_condition=notification.source_condition,
        source_ref=notification.source_ref,
        source_version=notification.source_version,
        facts=dict(facts or {}),
        occurred_at=occurred_at or timezone.now(),
        retention_until=notification.retention_until,
    )


def _push_after_commit(notification: UserNotification) -> None:
    notification_pk = notification.pk
    category = notification.category
    user_id = notification.user_id

    def _send() -> None:
        payload = {"id": notification_pk, "category": category}
        try:
            from django_eventstream import send_event

            send_event(f"user-{user_id}", "user-notification", payload)
        except ImportError:
            return
        except Exception:
            logger.warning(
                "operator_notification.user_push_failed user=%s",
                user_id,
                exc_info=True,
            )

    transaction.on_commit(_send)


def _push_batch_after_commit(*, user_id: int) -> None:
    def _send() -> None:
        try:
            from django_eventstream import send_event

            send_event(
                f"user-{user_id}",
                "user-notification",
                {"id": 0, "category": "system"},
            )
        except ImportError:
            return
        except Exception:
            logger.warning(
                "operator_notification.user_push_failed user=%s",
                user_id,
                exc_info=True,
            )

    transaction.on_commit(_send)


def _group_key(source_condition: str, source_ref: str, source_version: int) -> str:
    return f"{source_condition}:{source_ref}:v{source_version}"


def _dedupe_key(group_key: str, user_id: int) -> str:
    return f"{group_key}:owner:{user_id}"


def _resource_id(source_ref: str, prefix: str) -> int | None:
    head, separator, raw = str(source_ref or "").partition(":")
    if head != prefix or separator != ":" or not raw.isdigit():
        return None
    value = int(raw)
    return value if value > 0 else None


def _known_deep_link(source_condition: str, source_ref: str) -> str:
    if source_condition == ANNOUNCEMENT_REVIEW:
        resource_id = _resource_id(source_ref, "announcement")
        if resource_id is not None:
            return f"/announcements/{resource_id}#review"
    return ""


def _review_message(announcement: Announcement) -> str:
    message = announcement.body
    total = int((announcement.audience or {}).get("total") or 0)
    return f"{message}\n\nAudiência: {total} cliente(s)." if total else message


def _source_command(
    *,
    source_condition: str,
    source_ref: str,
    source_versions: set[int],
) -> MarketingCommandReceipt | None:
    if source_condition != ANNOUNCEMENT_REVIEW:
        return None
    announcement_id = _resource_id(source_ref, "announcement")
    if announcement_id is None:
        return None
    return (
        MarketingCommandReceipt.objects.filter(
            announcement_id=announcement_id,
            base_version__in=source_versions,
            state__in=(
                MarketingCommandReceipt.State.ACCEPTED,
                MarketingCommandReceipt.State.COMPLETED,
            ),
        )
        .order_by("-created_at", "-pk")
        .first()
    )


__all__ = [
    "ANNOUNCEMENT_REVIEW",
    "ESCALATION_OPS",
    "OWNER_PRODUCT",
    "AlertCreation",
    "acknowledge",
    "create_condition_alert",
    "mark_seen",
    "mark_seen_many",
    "push_user_notification",
    "reconcile_announcement_review",
    "reconcile_condition",
    "reconcile_user_notifications",
    "record_action",
]
