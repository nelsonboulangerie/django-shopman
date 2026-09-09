"""Fail-closed URL policy for Marketing links and externally fetched media.

Marketing content is rendered in an operator browser and later handed to social
providers.  An arbitrary URL can therefore disclose operator/recipient activity,
become an open redirect, or make a provider fetch an internal address.  Shopman
does not fetch these URLs.  It accepts only canonical storefront destinations and
media on an exact server-owned host allowlist; the provider sandbox still has to
prove its own redirect behaviour before a real rollout.
"""

from __future__ import annotations

import ipaddress
import logging
import re
from urllib.parse import parse_qsl, unquote, urlsplit

from django.conf import settings

from shopman.shop.services.marketing_contracts import MarketingContractError

logger = logging.getLogger(__name__)

_CUSTOMER_PATH = re.compile(r"^/(?:produto|oferta)/[A-Za-z0-9_.:-]{1,160}/?$")
_MEDIA_PATH = re.compile(r"^/[A-Za-z0-9_./@%+,:=-]{1,1000}$")
_MEDIA_QUERY_KEYS = frozenset({"auto", "crop", "dpr", "fit", "fm", "h", "q", "w"})
_UNSAFE_CHARS = re.compile(r"[\x00-\x20\x7f\\]")


def validate_customer_link(value: object, *, field: str = "content.link") -> str:
    """Accept only a canonical product/offer path on the configured storefront."""

    raw = str(value or "").strip()
    if not raw:
        return ""
    parsed = _split(raw, kind="link", field=field)
    _without_userinfo_or_nondefault_port(parsed, kind="link", field=field)
    _without_query_or_fragment(parsed, kind="link", field=field)
    _canonical_customer_path(parsed.path, field=field)

    if not parsed.scheme and not parsed.netloc:
        if not raw.startswith("/") or raw.startswith("//"):
            _reject("marketing_link_invalid", "link", field)
        return raw
    if parsed.scheme.lower() != "https":
        _reject("marketing_link_https_required", "link", field)

    configured = _storefront_origin()
    if configured is None or _origin(parsed) != configured:
        _reject("marketing_link_host_not_allowed", "link", field)
    _reject_private_literal(parsed.hostname, kind="link", field=field)
    return raw


def validate_media_url(value: object, *, field: str = "content.image_url") -> str:
    """Accept relative media or HTTPS media on an exact server-owned allowlist."""

    raw = str(value or "").strip()
    if not raw:
        return ""
    parsed = _split(raw, kind="media", field=field)
    _without_userinfo_or_nondefault_port(parsed, kind="media", field=field)
    if parsed.fragment:
        _reject("marketing_media_fragment_forbidden", "media", field)
    _safe_media_path(parsed.path, field=field)
    _safe_media_query(parsed.query, field=field)

    if not parsed.scheme and not parsed.netloc:
        if not raw.startswith("/") or raw.startswith("//"):
            _reject("marketing_media_invalid", "media", field)
        return raw
    if parsed.scheme.lower() != "https":
        _reject("marketing_media_https_required", "media", field)

    host = _normalized_host(parsed.hostname)
    _reject_private_literal(host, kind="media", field=field)
    if not host or host not in trusted_media_hosts():
        _reject("marketing_media_host_not_allowed", "media", field)
    return raw


def validate_media_redirect(
    source: object,
    destination: object,
    *,
    field: str = "content.image_url",
) -> str:
    """Policy for any future proxy/fetcher: redirects cannot cross origins.

    No current Marketing path follows redirects or fetches media server-side.  This
    helper freezes the required behaviour before a proxy can be introduced.
    """

    safe_source = validate_media_url(source, field=field)
    safe_destination = validate_media_url(destination, field=field)
    source_parts = _split(safe_source, kind="media", field=field)
    destination_parts = _split(safe_destination, kind="media", field=field)
    if _origin(source_parts) != _origin(destination_parts):
        _reject("marketing_media_redirect_forbidden", "media", field)
    return safe_destination


def trusted_media_hosts() -> frozenset[str]:
    """Exact hosts controlled by deployment, plus the canonical storefront host."""

    hosts: set[str] = set()
    base = _storefront_origin()
    if base is not None:
        hosts.add(base[1])
    configured = getattr(settings, "SHOPMAN_MARKETING_MEDIA_HOSTS", ()) or ()
    if isinstance(configured, str):
        configured = configured.split(",")
    for entry in configured:
        host = _normalized_host(str(entry).strip())
        if host:
            hosts.add(host)
    return frozenset(hosts)


def invalid_trusted_media_hosts() -> tuple[str, ...]:
    """Return unsafe config entries without DNS/network access."""

    configured = getattr(settings, "SHOPMAN_MARKETING_MEDIA_HOSTS", ()) or ()
    if isinstance(configured, str):
        configured = configured.split(",")
    invalid: list[str] = []
    for entry in configured:
        raw = str(entry).strip()
        host = _normalized_host(raw)
        if (
            not host
            or host != raw.lower().rstrip(".")
            or "*" in raw
            or ":" in raw
            or _is_non_public_host(host)
        ):
            invalid.append(raw or "<vazio>")
    return tuple(sorted(set(invalid)))


def safe_browser_media_url(value: object) -> str:
    """Never let an untrusted stored URL trigger a fetch in the operator browser."""

    try:
        return validate_media_url(value)
    except MarketingContractError:
        return ""


def safe_browser_customer_link(value: object) -> str:
    try:
        return validate_customer_link(value)
    except MarketingContractError:
        return ""


def canonical_customer_path(value: object) -> str | None:
    """Return the validated same-store path, or ``None`` for a safe fallback."""

    try:
        safe = validate_customer_link(value)
    except MarketingContractError:
        return None
    return urlsplit(safe).path if safe else None


def _storefront_origin() -> tuple[str, str, int | None] | None:
    raw = str(getattr(settings, "SHOPMAN_STOREFRONT_BASE_URL", "") or "").strip()
    if not raw:
        return None
    try:
        parsed = urlsplit(raw)
        return _origin(parsed) if parsed.scheme and parsed.hostname else None
    except ValueError:
        return None


def _split(raw: str, *, kind: str, field: str):
    if _UNSAFE_CHARS.search(raw):
        _reject(f"marketing_{kind}_invalid", kind, field)
    try:
        parsed = urlsplit(raw)
        # Accessing these properties forces malformed IPv6/port validation.
        _ = parsed.hostname
        _ = parsed.port
    except ValueError:
        _reject(f"marketing_{kind}_invalid", kind, field)
    if parsed.scheme and not parsed.netloc:
        _reject(f"marketing_{kind}_invalid", kind, field)
    if parsed.netloc and not parsed.scheme:
        _reject(f"marketing_{kind}_invalid", kind, field)
    return parsed


def _origin(parsed) -> tuple[str, str, int | None]:
    return (
        parsed.scheme.lower(),
        _normalized_host(parsed.hostname),
        None if parsed.port in (None, 443) else parsed.port,
    )


def _normalized_host(value: object) -> str:
    raw = str(value or "").strip().rstrip(".")
    if not raw:
        return ""
    try:
        return raw.encode("idna").decode("ascii").lower()
    except UnicodeError:
        return ""


def _without_userinfo_or_nondefault_port(parsed, *, kind: str, field: str) -> None:
    if parsed.username is not None or parsed.password is not None:
        _reject(f"marketing_{kind}_userinfo_forbidden", kind, field)
    if parsed.port not in (None, 443):
        _reject(f"marketing_{kind}_port_forbidden", kind, field)


def _without_query_or_fragment(parsed, *, kind: str, field: str) -> None:
    if parsed.query or parsed.fragment:
        _reject(f"marketing_{kind}_tracking_forbidden", kind, field)


def _canonical_customer_path(path: str, *, field: str) -> None:
    decoded = unquote(path)
    if decoded != path or not _CUSTOMER_PATH.fullmatch(path):
        _reject("marketing_link_path_not_canonical", "link", field)


def _safe_media_path(path: str, *, field: str) -> None:
    decoded = unquote(path)
    segments = decoded.split("/")
    if (
        not path
        or not _MEDIA_PATH.fullmatch(path)
        or any(segment in {".", ".."} for segment in segments)
        or "\\" in decoded
        or _UNSAFE_CHARS.search(decoded)
    ):
        _reject("marketing_media_path_invalid", "media", field)


def _safe_media_query(query: str, *, field: str) -> None:
    if not query:
        return
    try:
        pairs = parse_qsl(query, keep_blank_values=True, strict_parsing=True)
    except ValueError:
        _reject("marketing_media_tracking_query", "media", field)
    if not pairs or any(key not in _MEDIA_QUERY_KEYS for key, _value in pairs):
        _reject("marketing_media_tracking_query", "media", field)


def _reject_private_literal(host: object, *, kind: str, field: str) -> None:
    if _is_non_public_host(_normalized_host(host)):
        _reject(f"marketing_{kind}_private_host", kind, field)


def _is_non_public_host(host: str) -> bool:
    return (
        _is_non_global_literal(host)
        or host == "localhost"
        or host.endswith((".internal", ".local", ".localhost"))
        or "." not in host
    )


def _is_non_global_literal(host: str) -> bool:
    try:
        return not ipaddress.ip_address(host).is_global
    except ValueError:
        return False


def _reject(code: str, kind: str, field: str) -> None:
    logger.warning("marketing.url_rejected kind=%s code=%s field=%s", kind, code, field)
    detail = (
        "O link não atende à política segura de Marketing."
        if kind == "link"
        else "A imagem não atende à política segura de Marketing."
    )
    repair = (
        "Use o destino canônico da loja."
        if kind == "link"
        else "Use uma imagem HTTPS de um host autorizado pelo Platform Owner."
    )
    raise MarketingContractError(
        code=code,
        detail=detail,
        field_errors={field: (repair,)},
    )
