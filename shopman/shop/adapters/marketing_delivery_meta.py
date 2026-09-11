"""Shared Graph API implementation for public Instagram/Facebook publishing."""

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

_PROVIDER_ID = re.compile(r"^[A-Za-z0-9_.-]{1,110}$")


def instagram_available() -> bool:
    config = _config()
    return bool(
        _external_allowed()
        and getattr(settings, "SHOPMAN_MARKETING_INSTAGRAM_PUBLICATION_ENABLED", False)
        and config["ig_user_id"]
        and config["page_access_token"]
    )


def facebook_available() -> bool:
    config = _config()
    return bool(
        _external_allowed()
        and getattr(settings, "SHOPMAN_MARKETING_FACEBOOK_PUBLICATION_ENABLED", False)
        and config["page_id"]
        and config["page_access_token"]
    )


def send_instagram(*, artifact, target_key: str, idempotency_token: str) -> ProviderOutcome:
    del target_key, idempotency_token
    if not instagram_available():
        _not_attempted("instagram_publication_disabled")
    publication_format = _format(artifact, platform="instagram", allowed={"story", "feed"})
    if not _public_media_url(artifact.image_url):
        _not_attempted("instagram_media_required")

    config = _config()
    media_payload = {"image_url": artifact.image_url}
    if publication_format == "story":
        media_payload["media_type"] = "STORIES"
    else:
        media_payload["caption"] = _caption(artifact)

    try:
        container = request_json(
            method="POST",
            url=_graph_url(config, config["ig_user_id"], "media"),
            access_token=config["page_access_token"],
            timeout=config["timeout"],
            payload=media_payload,
            encoding="form",
        )
    except HTTPFailure as exc:
        raise _http_failure(exc, stage="prepare", provider="instagram") from None
    except TransportFailure:
        raise ProviderCallFailure(
            ProviderOutcomeKind.FAILED_RETRYABLE,
            "instagram_prepare_transport_failure",
        ) from None
    creation_id = _response_id(container)
    if not creation_id:
        raise ProviderCallFailure(
            ProviderOutcomeKind.FAILED_RETRYABLE,
            "instagram_prepare_response_invalid",
        )

    try:
        published = request_json(
            method="POST",
            url=_graph_url(config, config["ig_user_id"], "media_publish"),
            access_token=config["page_access_token"],
            timeout=config["timeout"],
            payload={"creation_id": creation_id},
            encoding="form",
        )
    except HTTPFailure as exc:
        raise _http_failure(exc, stage="publish", provider="instagram") from None
    except TransportFailure:
        # Bytes may have crossed the publish boundary. Never retry blindly.
        raise ProviderCallFailure(
            ProviderOutcomeKind.UNKNOWN,
            "instagram_publish_outcome_unknown",
        ) from None
    media_id = _response_id(published)
    if not media_id:
        raise ProviderCallFailure(
            ProviderOutcomeKind.UNKNOWN,
            "instagram_publish_response_invalid",
        )
    return ProviderOutcome(
        kind=ProviderOutcomeKind.ACCEPTED_UNCONFIRMED,
        code=f"instagram_{publication_format}_accepted",
        retryable=False,
        provider_receipt_ref=f"ig:{media_id}",
    )


def lookup_instagram(
    *, target_key: str, idempotency_token: str, provider_receipt_ref: str
) -> ProviderOutcome:
    del target_key, idempotency_token
    media_id = _receipt_id(provider_receipt_ref, prefix="ig:")
    if not instagram_available() or not media_id:
        _not_attempted("instagram_lookup_unavailable")
    return _lookup_meta(media_id, provider="instagram", prefix="ig:")


def send_facebook(*, artifact, target_key: str, idempotency_token: str) -> ProviderOutcome:
    del target_key, idempotency_token
    if not facebook_available():
        _not_attempted("facebook_publication_disabled")
    _format(artifact, platform="facebook", allowed={"feed"})
    if artifact.image_url and not _public_media_url(artifact.image_url):
        _not_attempted("facebook_media_url_not_public")
    config = _config()
    if artifact.image_url:
        edge = "photos"
        payload = {
            "url": artifact.image_url,
            "caption": _caption(artifact),
            "published": True,
        }
    else:
        edge = "feed"
        payload = {"message": _caption(artifact)}
        if artifact.link:
            payload["link"] = artifact.link
    try:
        result = request_json(
            method="POST",
            url=_graph_url(config, config["page_id"], edge),
            access_token=config["page_access_token"],
            timeout=config["timeout"],
            payload=payload,
            encoding="form",
        )
    except HTTPFailure as exc:
        raise _http_failure(exc, stage="publish", provider="facebook") from None
    except TransportFailure:
        raise ProviderCallFailure(
            ProviderOutcomeKind.UNKNOWN,
            "facebook_publish_outcome_unknown",
        ) from None
    post_id = _response_id(result, keys=("post_id", "id"))
    if not post_id:
        raise ProviderCallFailure(
            ProviderOutcomeKind.UNKNOWN,
            "facebook_publish_response_invalid",
        )
    return ProviderOutcome(
        kind=ProviderOutcomeKind.ACCEPTED_UNCONFIRMED,
        code="facebook_feed_accepted",
        retryable=False,
        provider_receipt_ref=f"fb:{post_id}",
    )


def lookup_facebook(
    *, target_key: str, idempotency_token: str, provider_receipt_ref: str
) -> ProviderOutcome:
    del target_key, idempotency_token
    post_id = _receipt_id(provider_receipt_ref, prefix="fb:")
    if not facebook_available() or not post_id:
        _not_attempted("facebook_lookup_unavailable")
    return _lookup_meta(post_id, provider="facebook", prefix="fb:")


def _lookup_meta(provider_id: str, *, provider: str, prefix: str) -> ProviderOutcome:
    config = _config()
    try:
        result = request_json(
            method="GET",
            url=f"{_graph_url(config, provider_id)}?fields=id",
            access_token=config["page_access_token"],
            timeout=config["timeout"],
        )
    except HTTPFailure as exc:
        raise _http_failure(exc, stage="lookup", provider=provider) from None
    except TransportFailure:
        raise ProviderCallFailure(
            ProviderOutcomeKind.FAILED_RETRYABLE,
            f"{provider}_lookup_transport_failure",
        ) from None
    resolved_id = _response_id(result)
    if resolved_id != provider_id:
        raise ProviderCallFailure(
            ProviderOutcomeKind.UNKNOWN,
            f"{provider}_lookup_response_invalid",
        )
    return ProviderOutcome(
        kind=ProviderOutcomeKind.CONFIRMED,
        code=f"{provider}_publication_confirmed",
        retryable=False,
        provider_receipt_ref=f"{prefix}{provider_id}",
    )


def _format(artifact, *, platform: str, allowed: set[str]) -> str:
    if artifact.platform != platform:
        _not_attempted(f"{platform}_artifact_mismatch")
    value = str(dict(artifact.provider_fields).get("publication_format") or "").lower()
    if value not in allowed:
        _not_attempted(f"{platform}_publication_format_missing_or_invalid")
    return value


def _caption(artifact) -> str:
    tags = " ".join(f"#{tag}" for tag in artifact.hashtags)
    parts = [artifact.body, tags]
    if artifact.link and artifact.link not in artifact.body:
        parts.append(artifact.link)
    return "\n\n".join(part for part in parts if part)


def _public_media_url(value: str) -> bool:
    try:
        parsed = urlsplit(str(value or ""))
    except ValueError:
        return False
    return parsed.scheme.lower() == "https" and bool(parsed.hostname)


def _config() -> dict:
    raw = getattr(settings, "SHOPMAN_MARKETING_META", {}) or {}
    return {
        "api_base": str(raw.get("api_base") or "https://graph.facebook.com").rstrip("/"),
        "api_version": str(raw.get("api_version") or "v21.0").strip("/"),
        "ig_user_id": str(raw.get("ig_user_id") or ""),
        "page_id": str(raw.get("page_id") or ""),
        "page_access_token": str(raw.get("page_access_token") or ""),
        "timeout": max(1, int(raw.get("timeout") or 30)),
    }


def _external_allowed() -> bool:
    return not settings.DEBUG or bool(
        getattr(settings, "SHOPMAN_ALLOW_EXTERNAL_IN_DEBUG", False)
    )


def _graph_url(config: dict, object_id: str, edge: str = "") -> str:
    path = f"/{quote(str(object_id), safe='')}"
    if edge:
        path += f"/{quote(edge, safe='')}"
    return f"{config['api_base']}/{config['api_version']}{path}"


def _response_id(payload: dict, *, keys=("id",)) -> str:
    for key in keys:
        value = str(payload.get(key) or "")
        if _PROVIDER_ID.fullmatch(value):
            return value
    return ""


def _receipt_id(value: str, *, prefix: str) -> str:
    text = str(value or "")
    provider_id = text[len(prefix):] if text.startswith(prefix) else ""
    return provider_id if _PROVIDER_ID.fullmatch(provider_id) else ""


def _not_attempted(code: str) -> None:
    raise ProviderCallFailure(ProviderOutcomeKind.NOT_ATTEMPTED, code)


def _http_failure(exc: HTTPFailure, *, stage: str, provider: str) -> ProviderCallFailure:
    if exc.status == 429:
        return ProviderCallFailure(
            ProviderOutcomeKind.FAILED_RETRYABLE,
            f"{provider}_{stage}_rate_limited",
            exc.retry_after_seconds,
        )
    if 500 <= exc.status <= 599:
        kind = (
            ProviderOutcomeKind.UNKNOWN
            if stage == "publish"
            else ProviderOutcomeKind.FAILED_RETRYABLE
        )
        return ProviderCallFailure(kind, f"{provider}_{stage}_server_failure")
    return ProviderCallFailure(
        ProviderOutcomeKind.FAILED_FINAL,
        f"{provider}_{stage}_rejected",
    )
