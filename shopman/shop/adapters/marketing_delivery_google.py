"""Durable Google Business Profile standard-post publication lane."""

from __future__ import annotations

import re
from urllib.parse import quote, urlsplit

from django.conf import settings

from shopman.shop.adapters.marketing_delivery_http import (
    HTTPFailure,
    TransportFailure,
    request_json,
)
from shopman.shop.services.marketing_contracts import (
    ProviderCallFailure,
    ProviderOutcome,
    ProviderOutcomeKind,
)

_POST_ID = re.compile(r"^[A-Za-z0-9_.-]{1,100}$")


def is_available() -> bool:
    config = _config()
    return bool(
        _external_allowed()
        and getattr(settings, "SHOPMAN_MARKETING_GOOGLE_PUBLICATION_ENABLED", False)
        and config["access_token"]
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
            access_token=config["access_token"],
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
    try:
        result = request_json(
            method="GET",
            url=f"{_posts_url(config)}/{quote(post_id, safe='')}",
            access_token=config["access_token"],
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
        "account_id": str(raw.get("account_id") or ""),
        "location_id": str(raw.get("location_id") or ""),
        "timeout": max(1, int(raw.get("timeout") or 30)),
    }


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
