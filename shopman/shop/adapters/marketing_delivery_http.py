"""Small sanitized HTTP boundary shared by Marketing publication adapters."""

from __future__ import annotations

import json
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener

MAX_RESPONSE_BYTES = 64 * 1024


class _NoRedirect(HTTPRedirectHandler):
    """Never forward a bearer credential to a provider-selected host."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        del req, fp, code, msg, headers, newurl
        return None


_NO_REDIRECT_OPENER = build_opener(_NoRedirect)


@dataclass(slots=True)
class HTTPFailure(Exception):
    status: int
    retry_after_seconds: int | None = None


class TransportFailure(Exception):
    pass


def request_json(
    *,
    method: str,
    url: str,
    access_token: str,
    timeout: int,
    payload: dict | None = None,
    encoding: str = "json",
) -> dict:
    """Call one JSON endpoint without placing credentials in URL or errors."""

    data = None
    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {access_token}",
        "User-Agent": "Shopman-Marketing/1.0",
    }
    if payload is not None:
        if encoding == "form":
            normalized = {
                key: str(value).lower() if isinstance(value, bool) else value
                for key, value in payload.items()
            }
            data = urlencode(normalized).encode("utf-8")
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        else:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
    request = Request(url, data=data, headers=headers, method=method)
    try:
        with _open(request, timeout=timeout) as response:
            raw = response.read(MAX_RESPONSE_BYTES + 1)
    except HTTPError as exc:
        retry_after = _retry_after((exc.headers or {}).get("Retry-After", ""))
        # Never propagate the provider body: it may echo content or identifiers.
        raise HTTPFailure(exc.code, retry_after) from None
    except (URLError, TimeoutError, OSError, ValueError):
        raise TransportFailure from None
    if len(raw) > MAX_RESPONSE_BYTES:
        raise TransportFailure
    try:
        decoded = json.loads(raw.decode("utf-8")) if raw else {}
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise TransportFailure from None
    if not isinstance(decoded, dict):
        raise TransportFailure
    return decoded


def _open(request: Request, *, timeout: int):
    return _NO_REDIRECT_OPENER.open(request, timeout=timeout)


def _retry_after(value: str) -> int | None:
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None
