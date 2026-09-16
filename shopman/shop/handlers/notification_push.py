"""Entrega Web Push de alertas pessoais do backstage."""

from __future__ import annotations

import json
import re
from urllib.parse import urljoin, urlsplit

from django.conf import settings
from django.utils import timezone
from pywebpush import WebPushException, webpush
from requests import RequestException, Session
from shopman.orderman.exceptions import DirectiveTerminalError, DirectiveTransientError
from shopman.orderman.models import Directive

from shopman.shop.directives import NOTIFICATION_PUSH
from shopman.shop.models import (
    NotificationLifecycle,
    NotificationSeverity,
    PushSubscription,
    PushSurface,
    UserNotification,
)
from shopman.shop.services.observability import operational_event
from shopman.shop.services.push_endpoints import normalize_push_endpoint

_FINANCIAL_OR_SENSITIVE_CATEGORIES = frozenset({"order", "purchase", "report", "sign_in"})
_EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
_MONEY_RE = re.compile(r"(?i)(?:R\$\s*)?\d{1,3}(?:\.\d{3})*(?:,\d{2})")
_PHONE_RE = re.compile(r"(?<!\w)(?:\+?\d[\s().-]*){8,15}(?!\w)")
_DOCUMENT_RE = re.compile(r"(?<!\d)\d{3}[.\s-]?\d{3}[.\s-]?\d{3}[-\s]?\d{2}(?!\d)")
_CATEGORY_BASE_SETTING = {
    "campaign": "SHOPMAN_MARKETING_BASE_URL",
    "production": "SHOPMAN_PRODUCTION_BASE_URL",
    "order": "SHOPMAN_ORDERS_BASE_URL",
    "purchase": "SHOPMAN_PURCHASE_BASE_URL",
    "report": "SHOPMAN_BI_BASE_URL",
}


class _NoRedirectPushSession(Session):
    """Requests session that never follows a provider-controlled redirect."""

    def post(self, url, data=None, json=None, **kwargs):
        kwargs["allow_redirects"] = False
        return super().post(url, data=data, json=json, **kwargs)


class NotificationPushHandler:
    topic = NOTIFICATION_PUSH

    def handle(self, message: Directive) -> None:
        notification_id = (message.payload or {}).get("notification_id")
        if not isinstance(notification_id, int) or isinstance(notification_id, bool):
            raise DirectiveTerminalError("notification.push exige notification_id inteiro")

        notification = UserNotification.objects.filter(pk=notification_id).first()
        if notification is None or notification.lifecycle not in {
            NotificationLifecycle.UNSEEN,
            NotificationLifecycle.SEEN,
            NotificationLifecycle.ACKNOWLEDGED,
        }:
            return

        private_key, claims_email = _vapid_configuration()
        subscriptions = [
            subscription
            for subscription in PushSubscription.objects.filter(
                user_id=notification.user_id,
                disabled_at__isnull=True,
            ).order_by("pk")
            if notification.category in (subscription.categories or [])
            and not (
                subscription.surface_ref == PushSurface.POS
                and notification.severity != NotificationSeverity.CRITICAL
            )
        ]
        if not subscriptions:
            return

        payload = _push_payload(notification)
        ttl = 24 * 60 * 60 if notification.category == "report" else 60 * 60
        urgency = "high" if notification.severity == NotificationSeverity.CRITICAL else "normal"
        transient_failures = 0

        session = _NoRedirectPushSession()
        try:
            for subscription in subscriptions:
                endpoint = normalize_push_endpoint(subscription.endpoint)
                if endpoint is None:
                    _disable_subscription(subscription, status_code=None, reason="endpoint_not_allowed")
                    continue
                # ``last_success_at`` is health telemetry, never a receipt for a
                # particular message. Delivery is deliberately at-least-once:
                # after a partial/ambiguous failure every eligible endpoint is
                # attempted again, so a newer success can never erase an older
                # notification that was still pending.
                try:
                    webpush(
                        subscription_info={
                            "endpoint": endpoint,
                            "keys": {"p256dh": subscription.p256dh, "auth": subscription.auth},
                        },
                        data=json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                        vapid_private_key=private_key,
                        vapid_claims={"sub": f"mailto:{claims_email}"},
                        ttl=ttl,
                        headers={"Urgency": urgency},
                        timeout=max(1, int(getattr(settings, "VAPID_TIMEOUT_SECONDS", 10))),
                        requests_session=session,
                    )
                except WebPushException as exc:
                    status_code = getattr(getattr(exc, "response", None), "status_code", None)
                    if status_code in {404, 410}:
                        _disable_subscription(subscription, status_code=status_code)
                        continue
                    _record_failure(subscription, status_code=status_code)
                    if status_code == 429 or (isinstance(status_code, int) and status_code >= 500):
                        transient_failures += 1
                        continue
                    operational_event(
                        "notification.push.rejected",
                        subscription_id=subscription.pk,
                        surface_ref=subscription.surface_ref,
                        category=notification.category,
                        status_code=status_code,
                    )
                except RequestException:
                    _record_failure(subscription, status_code=None)
                    transient_failures += 1
                except Exception as exc:
                    _record_failure(subscription, status_code=None)
                    raise DirectiveTerminalError("notification.push falhou antes do transporte") from exc
                else:
                    subscription.last_success_at = timezone.now()
                    subscription.failures = 0
                    subscription.save(update_fields=["last_success_at", "failures"])
                    operational_event(
                        "notification.push.delivered",
                        subscription_id=subscription.pk,
                        surface_ref=subscription.surface_ref,
                        category=notification.category,
                        ttl=ttl,
                        urgency=urgency,
                    )
        finally:
            session.close()

        if transient_failures:
            raise DirectiveTransientError(
                f"notification.push teve {transient_failures} falha(s) transitória(s)"
            )


def _vapid_configuration() -> tuple[str, str]:
    private_key = str(getattr(settings, "VAPID_PRIVATE_KEY", "") or "").strip()
    public_key = str(getattr(settings, "VAPID_PUBLIC_KEY", "") or "").strip()
    claims_email = str(getattr(settings, "VAPID_CLAIMS_EMAIL", "") or "").strip()
    if not private_key or not public_key or not claims_email:
        raise DirectiveTerminalError("notification.push sem configuração VAPID completa")
    return private_key, claims_email


def _push_payload(notification: UserNotification) -> dict:
    body = ""
    if notification.category not in _FINANCIAL_OR_SENSITIVE_CATEGORIES:
        body = _scrub(notification.message, maximum=180)
    return {
        "schema_version": 1,
        "notification_id": notification.pk,
        "category": notification.category,
        "severity": notification.severity,
        "title": _scrub(notification.title, maximum=90) or "Novo aviso",
        "body": body,
        "action_url": _safe_action_url(
            notification.action_url,
            base_url=str(
                getattr(settings, _CATEGORY_BASE_SETTING.get(notification.category, ""), "")
                or ""
            ),
        ),
        "tag": (notification.group_key or f"notification-{notification.pk}")[:120],
        "badge_count": UserNotification.objects.filter(
            user_id=notification.user_id,
            lifecycle=NotificationLifecycle.UNSEEN,
        ).exclude(severity=NotificationSeverity.INFORMATION).count(),
    }


def _scrub(value: object, *, maximum: int) -> str:
    text = " ".join(str(value or "").split())
    text = _EMAIL_RE.sub("[email]", text)
    text = _DOCUMENT_RE.sub("[documento]", text)
    text = _PHONE_RE.sub("[telefone]", text)
    text = _MONEY_RE.sub("[valor]", text)
    return text[:maximum].rstrip()


def _safe_action_url(value: object, *, base_url: str = "") -> str:
    raw = str(value or "").strip()
    if not raw.startswith("/") or raw.startswith("//"):
        return "/"
    parsed = urlsplit(raw)
    if parsed.scheme or parsed.netloc or parsed.query:
        return "/"
    suffix = f"#{parsed.fragment}" if parsed.fragment else ""
    relative = f"{parsed.path}{suffix}"[:500]
    base = urlsplit(base_url.strip())
    if base.scheme != "https" or not base.netloc or base.username or base.password:
        return relative
    return urljoin(f"{base.scheme}://{base.netloc}/", relative.lstrip("/"))[:500]


def _record_failure(subscription: PushSubscription, *, status_code: int | None) -> None:
    subscription.failures = min(subscription.failures + 1, 32767)
    subscription.save(update_fields=["failures"])
    operational_event(
        "notification.push.failed",
        subscription_id=subscription.pk,
        surface_ref=subscription.surface_ref,
        failures=subscription.failures,
        status_code=status_code,
    )


def _disable_subscription(
    subscription: PushSubscription,
    *,
    status_code: int | None,
    reason: str = "provider_gone",
) -> None:
    subscription.failures = min(subscription.failures + 1, 32767)
    subscription.disabled_at = timezone.now()
    subscription.save(update_fields=["failures", "disabled_at"])
    operational_event(
        "notification.push.disabled",
        subscription_id=subscription.pk,
        surface_ref=subscription.surface_ref,
        failures=subscription.failures,
        status_code=status_code,
        reason=reason,
    )


__all__ = ["NotificationPushHandler"]
