"""Single privacy boundary for logs and external error telemetry.

Observability is not a second data store.  This module deliberately prefers
losing diagnostic detail over leaking customer content, contact data or bearer
material.  Technical request/resource references may remain; values carried by
sensitive fields never do.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any
from urllib.parse import urlsplit, urlunsplit

REDACTED = "[redacted]"

_SENSITIVE_KEYS = frozenset({
    "authorization",
    "body",
    "content",
    "cookie",
    "cookies",
    "customer",
    "customer_data",
    "data",
    "email",
    "idempotency_key",
    "members",
    "password",
    "phone",
    "prompt",
    "provider_body",
    "provider_response",
    "raw_error",
    "recipient",
    "request_body",
    "secret",
    "set_cookie",
    "target_key",
    "token",
})
_URL_KEYS = frozenset({"url", "request_url", "source_url"})
_SAFE_SENTRY_HEADERS = frozenset({"content-type", "x-request-id"})

_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_PHONE_RE = re.compile(r"(?<!\w)(?:\+?\d[\d\s().-]{7,}\d)(?!\w)")
_BEARER_RE = re.compile(r"(?i)\b(?:bearer|basic)\s+[A-Za-z0-9._~+/=-]+")
_SECRET_ASSIGNMENT_RE = re.compile(
    r"(?i)\b(token|password|secret|api[_-]?key|authorization)\s*[:=]\s*[^\s,;]+"
)
_URL_RE = re.compile(r"https?://[^\s<>\]\[\"']+")


def redact_text(value: str) -> str:
    """Remove common PII/secret shapes and URL query/fragment values."""

    text = _EMAIL_RE.sub("[email]", str(value))
    text = _PHONE_RE.sub("[phone]", text)
    text = _BEARER_RE.sub(REDACTED, text)
    text = _SECRET_ASSIGNMENT_RE.sub(lambda match: f"{match.group(1)}={REDACTED}", text)
    return _URL_RE.sub(lambda match: strip_url_query(match.group(0)), text)


def strip_url_query(value: str) -> str:
    """Keep scheme/host/path while dropping query and fragment defensively."""

    try:
        split = urlsplit(str(value))
    except (TypeError, ValueError):
        return REDACTED
    if not split.scheme or not split.netloc:
        return str(value).split("?", 1)[0].split("#", 1)[0]
    return urlunsplit((split.scheme, split.netloc, split.path, "", ""))


def redact_observability_value(value: Any, *, key: str = "") -> Any:
    """Recursively sanitize a value before it enters logs or error telemetry."""

    normalized_key = str(key).strip().lower().replace("-", "_")
    if normalized_key in _SENSITIVE_KEYS:
        return REDACTED
    if value is None or isinstance(value, bool | int | float):
        return value
    if isinstance(value, str):
        if normalized_key in _URL_KEYS:
            return strip_url_query(value)
        return redact_text(value)
    if isinstance(value, Mapping):
        return {
            str(nested_key): redact_observability_value(
                nested_value,
                key=str(nested_key),
            )
            for nested_key, nested_value in value.items()
        }
    if isinstance(value, (list, tuple, set)):
        return [redact_observability_value(item) for item in value]
    return redact_text(str(value))


def scrub_sentry_event(event: Any) -> Any:
    """Allowlist request metadata and redact every remaining Sentry surface."""

    if not isinstance(event, dict):
        return event

    request = event.get("request")
    if isinstance(request, dict):
        url = request.get("url")
        original_headers = request.get("headers")
        request.clear()
        if isinstance(url, str):
            request["url"] = strip_url_query(url)
        if isinstance(original_headers, Mapping):
            request["headers"] = _safe_headers(original_headers)
    elif request is not None:
        event.pop("request", None)

    # Even with send_default_pii=False, integrations and explicit scope data can
    # repopulate these fields.  Keep the local boundary independent of SDK policy.
    event.pop("user", None)

    for field in tuple(event):
        if field == "request":
            continue
        event[field] = redact_observability_value(event[field], key=field)
    return event


def _safe_headers(headers: Mapping[Any, Any]) -> dict[str, str]:
    safe: dict[str, str] = {}
    for key, value in headers.items():
        normalized = str(key).strip().lower()
        if normalized in _SAFE_SENTRY_HEADERS and isinstance(value, str):
            safe[normalized] = redact_text(value)[:200]
    return safe


__all__ = [
    "REDACTED",
    "redact_observability_value",
    "redact_text",
    "scrub_sentry_event",
    "strip_url_query",
]
