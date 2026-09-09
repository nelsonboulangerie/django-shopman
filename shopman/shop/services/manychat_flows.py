"""Read-only ManyChat flow catalog with explicit freshness and failure states.

The opaque ``flow_ns`` is never typed or trusted by an operator command.  A
configuration write may use only a reference present in a *fresh*, successful
catalog response.  A last-known-good snapshot remains useful for diagnosis,
but is deliberately not mutation authority.
"""

from __future__ import annotations

import hashlib
import json
import logging
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal, cast
from urllib.error import HTTPError, URLError

from django.core.cache import cache
from django.utils import timezone

logger = logging.getLogger(__name__)

_DEFAULT_BASE_URL = "https://api.manychat.com/fb"
_CACHE_KEY = "shopman.manychat.flows.v2"
_LAST_GOOD_KEY = "shopman.manychat.flows.last-good.v2"
_CACHE_TTL = 300
_FAILURE_CACHE_TTL = 30
_LAST_GOOD_TTL = 86_400

CatalogState = Literal["fresh", "stale", "unavailable", "not_configured"]


@dataclass(frozen=True, slots=True)
class FlowCatalog:
    flows: tuple[tuple[str, str], ...]
    state: CatalogState
    checked_at: datetime
    facts_as_of: datetime | None
    fresh_until: datetime | None
    catalog_hash: str
    reason_code: str = ""

    @property
    def mutation_safe(self) -> bool:
        return (
            self.state == "fresh"
            and self.fresh_until is not None
            and self.fresh_until > self.checked_at
        )

    def contains(self, flow_ns: str) -> bool:
        return any(candidate == flow_ns for candidate, _name in self.flows)


@dataclass(frozen=True, slots=True)
class _FetchResult:
    state: Literal["fresh", "unavailable", "not_configured"]
    flows: tuple[tuple[str, str], ...] = ()
    reason_code: str = ""


def flow_catalog(
    *,
    force: bool = False,
    now: datetime | None = None,
) -> FlowCatalog:
    """Return catalog facts without flattening outage into a known empty list."""

    clock = _aware_now(now)
    if not force:
        cached = _catalog_from_cache(cache.get(_CACHE_KEY), checked_at=clock)
        if cached is not None:
            return cached

    fetched = _coerce_fetch_result(_fetch())
    if fetched.state == "fresh":
        facts_as_of = clock
        fresh_until = clock + timedelta(seconds=_CACHE_TTL)
        catalog = FlowCatalog(
            flows=fetched.flows,
            state="fresh",
            checked_at=clock,
            facts_as_of=facts_as_of,
            fresh_until=fresh_until,
            catalog_hash=_catalog_hash(fetched.flows),
        )
        encoded = _catalog_to_cache(catalog)
        cache.set(_CACHE_KEY, encoded, _CACHE_TTL)
        cache.set(_LAST_GOOD_KEY, encoded, _LAST_GOOD_TTL)
        return catalog

    last_good = _catalog_from_cache(cache.get(_LAST_GOOD_KEY), checked_at=clock)
    if last_good is not None:
        degraded = FlowCatalog(
            flows=last_good.flows,
            state="stale",
            checked_at=clock,
            facts_as_of=last_good.facts_as_of,
            fresh_until=last_good.fresh_until,
            catalog_hash=last_good.catalog_hash,
            reason_code=fetched.reason_code,
        )
        cache.set(_CACHE_KEY, _catalog_to_cache(degraded), _FAILURE_CACHE_TTL)
        return degraded

    catalog = FlowCatalog(
        flows=(),
        state=fetched.state,
        checked_at=clock,
        facts_as_of=None,
        fresh_until=None,
        catalog_hash="",
        reason_code=fetched.reason_code,
    )
    cache.set(_CACHE_KEY, _catalog_to_cache(catalog), _FAILURE_CACHE_TTL)
    return catalog


def list_flows(*, force: bool = False) -> tuple[tuple[str, str], ...]:
    """Compatibility view: only a fresh, authoritative list is selectable."""

    catalog = flow_catalog(force=force)
    return catalog.flows if catalog.mutation_safe else ()


def flow_name(ns: str) -> str:
    """Return a verified current name, or empty when current truth is unknown."""

    if not ns:
        return ""
    for candidate, name in list_flows():
        if candidate == ns:
            return name
    return ""


def _fetch() -> _FetchResult:
    from django.conf import settings

    config = getattr(settings, "SHOPMAN_MANYCHAT", {}) or {}
    token = str(
        config.get("api_token") or getattr(settings, "MANYCHAT_API_TOKEN", "") or ""
    ).strip()
    if not token:
        return _FetchResult(
            state="not_configured",
            reason_code="manychat_credential_missing",
        )

    base_url = str(config.get("base_url") or _DEFAULT_BASE_URL).rstrip("/")
    try:
        timeout = max(1, min(int(config.get("timeout") or 8), 30))
    except (TypeError, ValueError):
        timeout = 8
    request = urllib.request.Request(
        f"{base_url}/page/getFlows",
        headers={"Authorization": f"Bearer {token}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        logger.warning("manychat.flows_http_error status=%s", exc.code)
        return _FetchResult(
            state="unavailable",
            reason_code="manychat_catalog_http_error",
        )
    except URLError:
        logger.warning("manychat.flows_unreachable")
        return _FetchResult(
            state="unavailable",
            reason_code="manychat_catalog_unreachable",
        )
    except (ValueError, OSError):
        logger.warning("manychat.flows_unreadable", exc_info=True)
        return _FetchResult(
            state="unavailable",
            reason_code="manychat_catalog_unreadable",
        )

    if not isinstance(payload, dict):
        logger.warning("manychat.flows_unreadable")
        return _FetchResult(
            state="unavailable",
            reason_code="manychat_catalog_unreadable",
        )
    data = payload.get("data") or {}
    rows = data.get("flows") if isinstance(data, dict) else data
    pairs = [
        (str(row.get("ns")), str(row.get("name") or row.get("ns")))
        for row in (rows or [])
        if isinstance(row, dict)
        and row.get("ns")
        and _row_is_active(row)
    ]
    return _FetchResult(
        state="fresh",
        flows=tuple(sorted(set(pairs), key=lambda pair: pair[1].lower())),
    )


def _row_is_active(row: dict) -> bool:
    """Exclude an explicitly inactive provider row; listed rows are otherwise usable."""

    active = row.get("is_active")
    normalized_active = active.strip().lower() if isinstance(active, str) else active
    if normalized_active is not None and normalized_active not in (
        True,
        1,
        "1",
        "true",
        "active",
    ):
        return False
    status = str(row.get("status") or "").strip().lower()
    return status not in {"inactive", "disabled", "archived", "deleted"}


def _coerce_fetch_result(value) -> _FetchResult:
    # Keep old test/extensions that replace ``_fetch`` with the historical tuple.
    if isinstance(value, _FetchResult):
        return value
    return _FetchResult(
        state="fresh",
        flows=tuple(tuple(pair) for pair in (value or ())),
    )


def _catalog_hash(flows: tuple[tuple[str, str], ...]) -> str:
    payload = json.dumps(
        flows,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _catalog_to_cache(catalog: FlowCatalog) -> dict:
    return {
        "flows": [list(pair) for pair in catalog.flows],
        "state": catalog.state,
        "checked_at": catalog.checked_at.isoformat(),
        "facts_as_of": catalog.facts_as_of.isoformat() if catalog.facts_as_of else "",
        "fresh_until": catalog.fresh_until.isoformat() if catalog.fresh_until else "",
        "catalog_hash": catalog.catalog_hash,
        "reason_code": catalog.reason_code,
    }


def _catalog_from_cache(value, *, checked_at: datetime) -> FlowCatalog | None:
    if not isinstance(value, dict):
        return None
    try:
        state_value = str(value["state"])
        if state_value not in {"fresh", "stale", "unavailable", "not_configured"}:
            return None
        cached_checked_at = datetime.fromisoformat(str(value["checked_at"]))
        facts_as_of = _optional_datetime(value.get("facts_as_of"))
        fresh_until = _optional_datetime(value.get("fresh_until"))
        flows = tuple(
            (str(pair[0]), str(pair[1]))
            for pair in value.get("flows", ())
            if isinstance(pair, (list, tuple)) and len(pair) == 2
        )
        catalog_hash = str(value.get("catalog_hash") or "")
    except (KeyError, TypeError, ValueError):
        return None
    state = cast(CatalogState, state_value)
    if state == "fresh" and (fresh_until is None or fresh_until <= checked_at):
        state = "stale"
    return FlowCatalog(
        flows=flows,
        state=state,
        checked_at=cached_checked_at,
        facts_as_of=facts_as_of,
        fresh_until=fresh_until,
        catalog_hash=catalog_hash,
        reason_code=str(value.get("reason_code") or ""),
    )


def _optional_datetime(value) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(str(value))
    return parsed if timezone.is_aware(parsed) else timezone.make_aware(parsed)


def _aware_now(value: datetime | None) -> datetime:
    clock = value or timezone.now()
    if timezone.is_naive(clock):
        return timezone.make_aware(clock)
    return clock
