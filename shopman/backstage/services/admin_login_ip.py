"""Explicit deployment boundary for Admin throttling, independent of BFF hops."""
from ipaddress import ip_address

from django.conf import settings
from django.core.checks import Error, Tags, register

SOURCES = {"direct": "REMOTE_ADDR", "do": "HTTP_DO_CONNECTING_IP"}


def canonical_ip(value: str) -> str:
    """Accept exactly one address, without a port, zone or forwarded chain."""
    if not isinstance(value, str) or not value or "%" in value:
        raise ValueError("Invalid Admin client IP")
    address = ip_address(value.strip())
    # IPv4-mapped IPv6 must share the IPv4 bucket.
    return str(getattr(address, "ipv4_mapped", None) or address)


def admin_login_ip(request) -> str:
    source = getattr(settings, "SHOPMAN_ADMIN_LOGIN_IP_SOURCE", "")
    if source not in SOURCES:
        raise ValueError("Admin client IP source is not configured")
    # Selecting `do` asserts a verified ingress boundary. Header presence alone
    # never enables this mode; no XFF fallback or guessed proxy depth is used.
    return canonical_ip(request.META.get(SOURCES[source], ""))


@register(Tags.security, deploy=True)
def check_admin_login_ip_source(app_configs, **kwargs):
    middleware = "shopman.backstage.middleware_admin_login.AdminLoginRateLimitMiddleware"
    if middleware not in settings.MIDDLEWARE:
        return []
    if getattr(settings, "SHOPMAN_ADMIN_LOGIN_IP_SOURCE", "") in SOURCES:
        return []
    return [Error(
        "Admin login requires an explicit client IP source.",
        hint="Set SHOPMAN_ADMIN_LOGIN_IP_SOURCE to direct for a direct connection, or do only after verifying the Admin ingress boundary.",
        id="backstage.E001",
    )]
