"""Fail-closed validation for browser-issued Web Push endpoints.

``PushSubscription.endpoint`` is client-controlled input and later becomes an
outbound POST target.  HTTPS alone is therefore not a security boundary: an
attacker could otherwise turn the directive worker into an SSRF primitive.

The allowlist follows the browser vendors' own endpoint guidance:

* Apple: ``https://*.push.apple.com``
  https://developer.apple.com/documentation/usernotifications/sending-web-push-notifications-in-web-apps-and-browsers
* Microsoft: subdomains of ``notify.windows.com``
  https://learn.microsoft.com/windows/apps/develop/notifications/push-notifications/wns-overview
* Google FCM: ``fcm.googleapis.com``
  https://firebase.google.com/docs/cloud-messaging/network-configuration
* Mozilla Autopush: ``updates.push.services.mozilla.com``
  https://github.com/mozilla-services/autopush/blob/master/docs/http.rst

Validation is deliberately repeated immediately before transport.  Database
rows may predate this rule, so API-time validation alone is insufficient.
"""

from __future__ import annotations

from urllib.parse import urlsplit

_EXACT_PUSH_HOSTS = frozenset({
    "fcm.googleapis.com",
    "updates.push.services.mozilla.com",
})
_PUSH_HOST_SUFFIXES = (
    ".push.apple.com",
    ".notify.windows.com",
)


def normalize_push_endpoint(value: object) -> str | None:
    """Return a canonical safe endpoint, or ``None`` without doing DNS/I/O."""

    endpoint = str(value or "").strip()
    if not endpoint or len(endpoint) > 4096:
        return None
    try:
        parsed = urlsplit(endpoint)
        hostname = (parsed.hostname or "").rstrip(".").lower()
        port = parsed.port
    except ValueError:
        return None
    if (
        parsed.scheme != "https"
        or not parsed.netloc
        or parsed.username
        or parsed.password
        or port not in (None, 443)
        or parsed.fragment
        or not hostname
    ):
        return None
    if hostname not in _EXACT_PUSH_HOSTS and not any(
        hostname.endswith(suffix) and hostname != suffix[1:]
        for suffix in _PUSH_HOST_SUFFIXES
    ):
        return None
    return endpoint


__all__ = ["normalize_push_endpoint"]
