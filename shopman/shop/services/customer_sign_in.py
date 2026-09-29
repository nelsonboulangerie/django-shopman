"""Alertas e gestão dos acessos de clientes no Storefront.

``UserNotification`` já é o livro pessoal, exportável e apagado com a conta;
cada login acrescenta uma linha com prazo próprio e o identificador opaco da
sessão. A chave da sessão nunca sai do cofre do Django nem é gravada no alerta.
"""

from __future__ import annotations

import hmac
import logging
from datetime import timedelta

from django.contrib.sessions.models import Session
from django.core import signing
from django.core.exceptions import ObjectDoesNotExist
from django.utils import timezone

logger = logging.getLogger(__name__)

REQUEST_METHOD_ATTR = "shopman_customer_sign_in_method"
SOURCE_CONDITION = "customer_sign_in"
RETENTION = timedelta(days=180)
MAX_RECENT_ACCESSES = 20

METHOD_LABELS = {
    "access_link": "link de acesso",
    "otp": "código de verificação",
    "passkey": "chave de acesso",
    "trusted_device": "dispositivo reconhecido",
}


def mark_method(request, method: str) -> None:
    """Marque uma requisição imediatamente antes de ela abrir a sessão."""

    if request is not None:
        setattr(request, REQUEST_METHOD_ATTR, method)


def _session_ref(session_key: str) -> str:
    """Identificador comparável sem persistir a credencial da sessão."""

    if not session_key:
        return ""
    return signing.salted_hmac(
        "shopman.customer-session-ref",
        session_key,
        algorithm="sha256",
    ).hexdigest()[:40]


def _device_label(request) -> str:
    try:
        from shopman.doorman.services.device_trust import describe_user_agent

        label = describe_user_agent(str(request.META.get("HTTP_USER_AGENT", "") or ""))
        return (label or "Dispositivo não identificado").replace(" / ", " no ")[:120]
    except Exception:  # pragma: no cover - o alerta nunca derruba o login
        logger.warning("customer_sign_in.device_label_failed", exc_info=True)
        return "Dispositivo não identificado"


def _approximate_city(request) -> str:
    """Local aproximado calculado pela base local, sem chamada de rede."""

    try:
        from shopman.shop.services.auth import client_ip
        from shopman.shop.services.ip_location import approximate_city

        city = approximate_city(client_ip(request))
        return city.label if city else ""
    except Exception:  # pragma: no cover - ausência da base é degradação segura
        logger.warning("customer_sign_in.location_failed", exc_info=True)
        return ""


def on_user_logged_in(sender, request=None, user=None, **kwargs) -> None:
    """Crie um alerta só para as portas de cliente marcadas pelo orquestrador."""

    method = getattr(request, REQUEST_METHOD_ATTR, "") if request is not None else ""
    if not method or user is None or getattr(user, "is_staff", False):
        return
    try:
        customer_link = user.doorman_customer_user
    except ObjectDoesNotExist:
        return
    if customer_link is None:  # pragma: no cover - OneToOne nunca devolve None
        return
    record(request=request, user=user, method=method)


def record(*, request, user, method: str):
    """Persista e publique o aviso. Falha nunca impede a pessoa de entrar."""

    try:
        from shopman.shop.models import (
            NotificationCategory,
            NotificationSeverity,
            UserNotification,
        )
        from shopman.shop.services.user_notifications import push_user_notification

        session = getattr(request, "session", None)
        if session is None:
            return None
        if not session.session_key:
            session.save()
        ref = _session_ref(session.session_key or "")
        if not ref:
            return None

        now = timezone.now()
        label = _device_label(request)
        city = _approximate_city(request)
        method_label = METHOD_LABELS.get(method, "acesso à conta")
        when = timezone.localtime(now).strftime("%d/%m/%Y às %H:%M")
        lines = [f"{label} · {when}"]
        if city:
            lines.append(f"Próximo a {city}")
        lines.append(
            "Se foi você, não precisa fazer nada. Se não reconhece, encerre o acesso em Segurança e dados."
        )

        notification = UserNotification.objects.create(
            user=user,
            category=NotificationCategory.SIGN_IN,
            severity=NotificationSeverity.INFORMATION,
            title="Novo acesso na sua conta",
            message="\n".join(lines),
            action_url="/conta/seguranca",
            action_data={
                "session_ref": ref,
                "method": method,
                "method_label": method_label,
                "device_label": label,
                "approximate_city": city,
            },
            source_condition=SOURCE_CONDITION,
            source_ref=ref,
            retention_until=now + RETENTION,
        )
        push_user_notification(notification)
        return notification
    except Exception:  # pragma: no cover - segurança não pode virar negação de serviço
        logger.warning(
            "customer_sign_in.record_failed user=%s",
            getattr(user, "pk", None),
            exc_info=True,
        )
        return None


def _active_sessions(user) -> dict[str, Session]:
    active: dict[str, Session] = {}
    for session in Session.objects.filter(expire_date__gte=timezone.now()).iterator():
        try:
            data = session.get_decoded()
        except Exception:
            logger.warning("customer_sign_in.session_undecodable")
            continue
        if str(data.get("_auth_user_id") or "") != str(user.pk):
            continue
        active[_session_ref(session.session_key)] = session
    return active


def list_accesses(*, user, current_session_key: str = "") -> list[dict]:
    """Acessos recentes, com estado ativo calculado no cofre de sessões."""

    from shopman.shop.models import UserNotification

    active = _active_sessions(user)
    current_ref = _session_ref(current_session_key)
    notifications = UserNotification.objects.filter(
        user=user,
        source_condition=SOURCE_CONDITION,
    ).order_by("-created_at", "-pk")[:MAX_RECENT_ACCESSES]

    rows: list[dict] = []
    seen: set[str] = set()
    for notification in notifications:
        data = notification.action_data if isinstance(notification.action_data, dict) else {}
        ref = str(data.get("session_ref") or notification.source_ref or "")
        if not ref:
            continue
        seen.add(ref)
        rows.append({
            "id": ref,
            "device_label": str(data.get("device_label") or "Dispositivo não identificado"),
            "method_label": str(data.get("method_label") or "acesso à conta"),
            "approximate_city": str(data.get("approximate_city") or ""),
            "created_at": notification.created_at.isoformat(),
            "created_at_display": timezone.localtime(notification.created_at).strftime("%d/%m/%Y às %H:%M"),
            "is_active": ref in active,
            "is_current": bool(current_ref and hmac.compare_digest(ref, current_ref)),
        })

    # Sessões anteriores ao deploy continuam gerenciáveis, sem inventar fatos.
    for ref in active:
        if ref in seen:
            continue
        rows.append({
            "id": ref,
            "device_label": "Dispositivo conectado",
            "method_label": "acesso anterior",
            "approximate_city": "",
            "created_at": None,
            "created_at_display": "Data não disponível",
            "is_active": True,
            "is_current": bool(current_ref and hmac.compare_digest(ref, current_ref)),
        })
    return rows


def revoke_session(*, user, access_ref: str) -> bool:
    """Encerre exatamente a sessão opaca escolhida pelo titular."""

    for ref, session in _active_sessions(user).items():
        if hmac.compare_digest(ref, str(access_ref)):
            session.delete()
            return True
    return False


def revoke_other_sessions(*, user, current_session_key: str = "") -> int:
    current_ref = _session_ref(current_session_key)
    revoked = 0
    for ref, session in _active_sessions(user).items():
        if current_ref and hmac.compare_digest(ref, current_ref):
            continue
        session.delete()
        revoked += 1
    return revoked


__all__ = [
    "SOURCE_CONDITION",
    "list_accesses",
    "mark_method",
    "on_user_logged_in",
    "record",
    "revoke_other_sessions",
    "revoke_session",
]
