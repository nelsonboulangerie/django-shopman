"""
Notification dispatch — registry + send.

Adapters are function-style modules in shopman.adapters.notification_*.
Each adapter exposes:
    send(recipient, template, context, **config) -> bool | dict | NotificationResult
    is_available(recipient, **config) -> bool

The registry maps backend names to adapter modules. Registration happens in
setup.py at startup. Callers use notify() to dispatch.
"""

from __future__ import annotations

import logging
from types import ModuleType
from typing import Any

logger = logging.getLogger(__name__)

from shopman.shop.protocols import NotificationResult

# Registry: backend name → adapter module (with a `send` function)
_adapters: dict[str, ModuleType] = {}


def register_backend(name: str, adapter: ModuleType) -> None:
    """Register a notification adapter module under `name`."""
    _adapters[name] = adapter
    logger.debug("Notification backend registered: %s", name)


def get_backend(name: str | None = None) -> ModuleType | None:
    """Resolve adapter module by name. Falls back to 'console' when name is None."""
    if name is None:
        name = "console"
    return _adapters.get(name)


def notify(
    *,
    event: str,
    recipient: str,
    context: dict[str, Any],
    backend: str | None = None,
) -> NotificationResult:
    """Dispatch a notification through the named adapter.

    Args:
        event: Template/event name (e.g. "order_accepted").
        recipient: Recipient identifier (phone, email, subscriber_id).
        context: Template variables passed to the adapter.
        backend: Backend name ("console", "email", "manychat", "sms").

    Returns:
        NotificationResult with success/error fields.
    """
    adapter = get_backend(backend)

    if not adapter:
        backend_name = backend or "default"
        logger.warning("Notification backend not found: %s", backend_name)
        return NotificationResult(success=False, error=f"Backend not found: {backend_name}")

    try:
        raw_result = adapter.send(recipient=recipient, template=event, context=context)
        result = _normalize_result(raw_result, backend=backend or "default")
        if result.success:
            # Nunca logar o destinatário nem fabricar um message_id a partir dele.
            # Bool confirma apenas aceite; prova do provider só existe quando o
            # próprio adapter devolve um identificador.
            logger.info("Notification accepted: event=%s backend=%s", event, backend or "default")
        else:
            logger.warning("Notification failed: %s -> %s", event, result.error)
        return result
    except Exception as e:
        logger.exception("Notification error: %s", event)
        return NotificationResult(success=False, error=str(e))


def _normalize_result(raw_result: Any, *, backend: str) -> NotificationResult:
    """Normalize legacy bool and richer provider results without inventing proof."""
    if isinstance(raw_result, NotificationResult):
        return raw_result
    if isinstance(raw_result, bool):
        if raw_result:
            return NotificationResult(success=True)
        return NotificationResult(success=False, error=f"Adapter {backend} returned False")
    if isinstance(raw_result, dict):
        success = raw_result.get("success") is True
        message_id = str(raw_result.get("message_id") or "").strip() or None
        error = str(raw_result.get("error") or "").strip() or None
        if success:
            return NotificationResult(success=True, message_id=message_id)
        return NotificationResult(
            success=False,
            error=error or f"Adapter {backend} returned an unsuccessful result",
        )
    return NotificationResult(
        success=False,
        error=f"Adapter {backend} returned an invalid result",
    )
