"""Durable Google Business Profile standard-post publication lane."""

from __future__ import annotations

import hashlib
import re
import threading
import time
from urllib.parse import quote, urlsplit

from django.conf import settings

from shopman.shop.adapters.marketing_delivery_http import (
    HTTPFailure,
    TransportFailure,
    request_form_json,
    request_json,
)
from shopman.shop.services.marketing_contracts import (
    ProviderCallFailure,
    ProviderOutcome,
    ProviderOutcomeKind,
)

_POST_ID = re.compile(r"^[A-Za-z0-9_.-]{1,100}$")
_TOKEN_CACHE: dict[str, tuple[str, float]] = {}
_TOKEN_LOCK = threading.Lock()
_TOKEN_EXPIRY_MARGIN_SECONDS = 60


def is_available() -> bool:
    config = _config()
    return bool(
        _external_allowed()
        and getattr(settings, "SHOPMAN_MARKETING_GOOGLE_PUBLICATION_ENABLED", False)
        and _has_credentials(config)
        and config["account_id"]
        and config["location_id"]
    )


def send(*, artifact, target_key: str, idempotency_token: str) -> ProviderOutcome:
    del target_key, idempotency_token
    if not is_available():
        _not_attempted("google_publication_disabled")
    fields = dict(artifact.provider_fields)
    if artifact.platform != "google_business" or fields.get("publication_format") != "standard":
        _not_attempted("google_publication_format_missing_or_invalid")

    if artifact.image_url and not _public_media_url(artifact.image_url):
        _not_attempted("google_media_url_not_public")
    config = _config()
    access_token = _access_token(config)
    payload: dict = {
        "languageCode": "pt-BR",
        "summary": _summary(artifact),
        "topicType": "STANDARD",
    }
    if artifact.link:
        payload["callToAction"] = {"actionType": "ORDER", "url": artifact.link}
    if artifact.image_url:
        payload["media"] = [{"mediaFormat": "PHOTO", "sourceUrl": artifact.image_url}]

    try:
        result = request_json(
            method="POST",
            url=_posts_url(config),
            access_token=access_token,
            timeout=config["timeout"],
            payload=payload,
        )
    except HTTPFailure as exc:
        raise _http_failure(exc, stage="publish") from None
    except TransportFailure:
        raise ProviderCallFailure(
            ProviderOutcomeKind.UNKNOWN,
            "google_publish_outcome_unknown",
        ) from None
    post_id = _post_id(result)
    if not post_id:
        raise ProviderCallFailure(
            ProviderOutcomeKind.UNKNOWN,
            "google_publish_response_invalid",
        )
    return ProviderOutcome(
        kind=ProviderOutcomeKind.ACCEPTED_UNCONFIRMED,
        code="google_standard_post_accepted",
        retryable=False,
        provider_receipt_ref=f"gbp:{post_id}",
    )


def lookup(
    *, target_key: str, idempotency_token: str, provider_receipt_ref: str
) -> ProviderOutcome:
    del target_key, idempotency_token
    post_id = _receipt_id(provider_receipt_ref)
    if not is_available() or not post_id:
        _not_attempted("google_lookup_unavailable")
    config = _config()
    access_token = _access_token(config)
    try:
        result = request_json(
            method="GET",
            url=f"{_posts_url(config)}/{quote(post_id, safe='')}",
            access_token=access_token,
            timeout=config["timeout"],
        )
    except HTTPFailure as exc:
        raise _http_failure(exc, stage="lookup") from None
    except TransportFailure:
        raise ProviderCallFailure(
            ProviderOutcomeKind.FAILED_RETRYABLE,
            "google_lookup_transport_failure",
        ) from None
    if _post_id(result) != post_id:
        raise ProviderCallFailure(
            ProviderOutcomeKind.UNKNOWN,
            "google_lookup_response_invalid",
        )
    return ProviderOutcome(
        kind=ProviderOutcomeKind.CONFIRMED,
        code="google_publication_confirmed",
        retryable=False,
        provider_receipt_ref=f"gbp:{post_id}",
    )


def _summary(artifact) -> str:
    tags = " ".join(f"#{tag}" for tag in artifact.hashtags)
    return "\n\n".join(part for part in (artifact.body, tags) if part)


def _public_media_url(value: str) -> bool:
    try:
        parsed = urlsplit(str(value or ""))
    except ValueError:
        return False
    return parsed.scheme.lower() == "https" and bool(parsed.hostname)


def _config() -> dict:
    raw = getattr(settings, "SHOPMAN_MARKETING_GOOGLE", {}) or {}
    return {
        "api_base": str(raw.get("api_base") or "https://mybusiness.googleapis.com").rstrip("/"),
        "api_version": str(raw.get("api_version") or "v4").strip("/"),
        "access_token": str(raw.get("access_token") or ""),
        "client_id": str(raw.get("client_id") or ""),
        "client_secret": str(raw.get("client_secret") or ""),
        "refresh_token": str(raw.get("refresh_token") or ""),
        "token_url": str(raw.get("token_url") or "https://oauth2.googleapis.com/token"),
        "account_id": str(raw.get("account_id") or ""),
        "location_id": str(raw.get("location_id") or ""),
        "timeout": max(1, int(raw.get("timeout") or 30)),
    }


def _has_credentials(config: dict) -> bool:
    return bool(
        config["access_token"]
        or (
            config["client_id"]
            and config["client_secret"]
            and config["refresh_token"]
        )
    )


def _access_token(config: dict) -> str:
    """Return a renewable bearer token, with static-token canary fallback."""

    if not (config["client_id"] and config["client_secret"] and config["refresh_token"]):
        return config["access_token"]

    cache_key = _token_cache_key(config)
    now = time.monotonic()
    cached = _TOKEN_CACHE.get(cache_key)
    if cached and cached[1] > now:
        return cached[0]

    with _TOKEN_LOCK:
        now = time.monotonic()
        cached = _TOKEN_CACHE.get(cache_key)
        if cached and cached[1] > now:
            return cached[0]
        try:
            response = request_form_json(
                url=config["token_url"],
                timeout=config["timeout"],
                payload={
                    "client_id": config["client_id"],
                    "client_secret": config["client_secret"],
                    "refresh_token": config["refresh_token"],
                    "grant_type": "refresh_token",
                },
            )
        except HTTPFailure as exc:
            kind = (
                ProviderOutcomeKind.FAILED_RETRYABLE
                if exc.status == 429 or 500 <= exc.status <= 599
                else ProviderOutcomeKind.FAILED_FINAL
            )
            raise ProviderCallFailure(
                kind,
                "google_oauth_refresh_unavailable"
                if kind == ProviderOutcomeKind.FAILED_RETRYABLE
                else "google_oauth_refresh_rejected",
                exc.retry_after_seconds,
            ) from None
        except TransportFailure:
            raise ProviderCallFailure(
                ProviderOutcomeKind.FAILED_RETRYABLE,
                "google_oauth_refresh_unavailable",
            ) from None

        token = str(response.get("access_token") or "").strip()
        token_type = str(response.get("token_type") or "Bearer").strip().lower()
        if not token or token_type != "bearer":
            raise ProviderCallFailure(
                ProviderOutcomeKind.FAILED_FINAL,
                "google_oauth_refresh_response_invalid",
            )
        try:
            expires_in = max(1, int(response.get("expires_in") or 300))
        except (TypeError, ValueError):
            expires_in = 300
        usable_for = max(1, expires_in - _TOKEN_EXPIRY_MARGIN_SECONDS)
        _TOKEN_CACHE[cache_key] = (token, now + usable_for)
        return token


def _token_cache_key(config: dict) -> str:
    material = "\0".join(
        (config["token_url"], config["client_id"], config["refresh_token"])
    ).encode("utf-8")
    return hashlib.sha256(material).hexdigest()


def _posts_url(config: dict) -> str:
    account = quote(config["account_id"], safe="")
    location = quote(config["location_id"], safe="")
    return (
        f"{config['api_base']}/{config['api_version']}/accounts/{account}"
        f"/locations/{location}/localPosts"
    )


def _post_id(payload: dict) -> str:
    name = str(payload.get("name") or "")
    post_id = name.rsplit("/", 1)[-1] if name else str(payload.get("id") or "")
    return post_id if _POST_ID.fullmatch(post_id) else ""


def _receipt_id(value: str) -> str:
    text = str(value or "")
    post_id = text[4:] if text.startswith("gbp:") else ""
    return post_id if _POST_ID.fullmatch(post_id) else ""


def _external_allowed() -> bool:
    return not settings.DEBUG or bool(
        getattr(settings, "SHOPMAN_ALLOW_EXTERNAL_IN_DEBUG", False)
    )


def _not_attempted(code: str) -> None:
    raise ProviderCallFailure(ProviderOutcomeKind.NOT_ATTEMPTED, code)


def _http_failure(exc: HTTPFailure, *, stage: str) -> ProviderCallFailure:
    if exc.status == 429:
        return ProviderCallFailure(
            ProviderOutcomeKind.FAILED_RETRYABLE,
            f"google_{stage}_rate_limited",
            exc.retry_after_seconds,
        )
    if 500 <= exc.status <= 599:
        kind = (
            ProviderOutcomeKind.UNKNOWN
            if stage == "publish"
            else ProviderOutcomeKind.FAILED_RETRYABLE
        )
        return ProviderCallFailure(kind, f"google_{stage}_server_failure")
    return ProviderCallFailure(
        ProviderOutcomeKind.FAILED_FINAL,
        f"google_{stage}_rejected",
    )
