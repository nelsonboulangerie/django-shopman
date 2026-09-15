"""TikTok Content Posting API adapter, inert until its dedicated gate is armed.

Only the photo Direct Post contract is implemented here.  The module is
deliberately usable in hermetic tests before TikTok is added to the selectable
capability catalog.  A credential or this module's presence never enables a
delivery by itself.
"""

from __future__ import annotations

import re
from urllib.parse import urlsplit

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

_PUBLISH_ID = re.compile(r"^[A-Za-z0-9_.:-]{1,160}$")
_PRIVACY = re.compile(r"^[A-Z_]{3,64}$")
_RETRYABLE_API_CODES = frozenset(
    {
        "internal_error",
        "rate_limit_exceeded",
        "server_error",
    }
)


def is_available() -> bool:
    config = _config()
    return bool(
        _external_allowed()
        and getattr(settings, "SHOPMAN_MARKETING_TIKTOK_PUBLICATION_ENABLED", False)
        and config["access_token"]
    )


def send(*, artifact, target_key: str, idempotency_token: str) -> ProviderOutcome:
    del target_key, idempotency_token
    if not is_available():
        _not_attempted("tiktok_publication_disabled")
    fields = dict(artifact.provider_fields)
    if artifact.platform != "tiktok" or artifact.delivery_kind != "publication" or artifact.format != "photo":
        _not_attempted("tiktok_photo_artifact_mismatch")
    if not _public_media_url(artifact.image_url):
        _not_attempted("tiktok_photo_url_not_public")

    privacy = str(fields.get("privacy_level") or "").strip()
    if not _PRIVACY.fullmatch(privacy):
        _not_attempted("tiktok_privacy_choice_required")
    required_booleans = (
        "disable_comment",
        "auto_add_music",
        "commercial_content",
        "brand_organic_toggle",
        "brand_content_toggle",
        "consent_confirmed",
    )
    if any(not isinstance(fields.get(name), bool) for name in required_booleans):
        _not_attempted("tiktok_explicit_choices_required")
    if not fields["consent_confirmed"]:
        _not_attempted("tiktok_consent_required")
    if fields["commercial_content"] and not (fields["brand_organic_toggle"] or fields["brand_content_toggle"]):
        _not_attempted("tiktok_commercial_disclosure_required")
    if fields["brand_content_toggle"] and privacy == "SELF_ONLY":
        _not_attempted("tiktok_branded_content_cannot_be_private")

    config = _config()
    creator = _creator_info(config)
    privacy_options = creator.get("privacy_level_options")
    if not isinstance(privacy_options, list) or privacy not in {str(item) for item in privacy_options}:
        _not_attempted("tiktok_privacy_choice_unavailable")
    if bool(creator.get("comment_disabled")) and not fields["disable_comment"]:
        _not_attempted("tiktok_comments_unavailable")

    post_info = {
        "title": _title(fields.get("title")),
        "description": _description(artifact),
        "disable_comment": fields["disable_comment"],
        "privacy_level": privacy,
        "auto_add_music": fields["auto_add_music"],
        "brand_content_toggle": fields["brand_content_toggle"],
        "brand_organic_toggle": fields["brand_organic_toggle"],
    }
    payload = {
        "post_info": post_info,
        "source_info": {
            "source": "PULL_FROM_URL",
            "photo_cover_index": 0,
            "photo_images": [artifact.image_url],
        },
        "post_mode": "DIRECT_POST",
        "media_type": "PHOTO",
    }
    try:
        response = request_json(
            method="POST",
            url=f"{config['api_base']}/v2/post/publish/content/init/",
            access_token=config["access_token"],
            timeout=config["timeout"],
            payload=payload,
        )
    except HTTPFailure as exc:
        raise _http_failure(exc, stage="publish") from None
    except TransportFailure:
        # The initialization request may already have created a post.  Reusing
        # the campaign idempotency token is not supported by TikTok, so lookup
        # or human reconciliation must win over a blind retry.
        raise ProviderCallFailure(
            ProviderOutcomeKind.UNKNOWN,
            "tiktok_publish_outcome_unknown",
        ) from None
    data = _response_data(response, stage="publish")
    publish_id = str(data.get("publish_id") or "")
    if not _PUBLISH_ID.fullmatch(publish_id):
        raise ProviderCallFailure(
            ProviderOutcomeKind.UNKNOWN,
            "tiktok_publish_response_invalid",
        )
    return ProviderOutcome(
        kind=ProviderOutcomeKind.ACCEPTED_UNCONFIRMED,
        code="tiktok_photo_accepted",
        retryable=False,
        provider_receipt_ref=f"tt:{publish_id}",
    )


def lookup(*, target_key: str, idempotency_token: str, provider_receipt_ref: str) -> ProviderOutcome:
    del target_key, idempotency_token
    publish_id = _receipt_id(provider_receipt_ref)
    if not is_available() or not publish_id:
        _not_attempted("tiktok_lookup_unavailable")
    config = _config()
    try:
        response = request_json(
            method="POST",
            url=f"{config['api_base']}/v2/post/publish/status/fetch/",
            access_token=config["access_token"],
            timeout=config["timeout"],
            payload={"publish_id": publish_id},
        )
    except HTTPFailure as exc:
        raise _http_failure(exc, stage="lookup") from None
    except TransportFailure:
        raise ProviderCallFailure(
            ProviderOutcomeKind.FAILED_RETRYABLE,
            "tiktok_lookup_transport_failure",
        ) from None
    data = _response_data(response, stage="lookup")
    status = str(data.get("status") or "").upper()
    if status == "FAILED":
        return ProviderOutcome(
            kind=ProviderOutcomeKind.FAILED_FINAL,
            code="tiktok_publication_failed",
            retryable=False,
            provider_receipt_ref=f"tt:{publish_id}",
        )
    if status not in {
        "PROCESSING_UPLOAD",
        "PROCESSING_DOWNLOAD",
        "SEND_TO_USER_INBOX",
        "PUBLISH_COMPLETE",
    }:
        return ProviderOutcome(
            kind=ProviderOutcomeKind.UNKNOWN,
            code="tiktok_publication_status_unknown",
            retryable=False,
            provider_receipt_ref=f"tt:{publish_id}",
        )
    post_id = next(
        (
            str(data.get(key) or "")
            for key in (
                "publicaly_available_post_id",
                "publicly_available_post_id",
                "post_id",
            )
            if data.get(key)
        ),
        "",
    )
    if status == "PUBLISH_COMPLETE" and post_id:
        return ProviderOutcome(
            kind=ProviderOutcomeKind.CONFIRMED,
            code="tiktok_publication_confirmed",
            retryable=False,
            provider_receipt_ref=f"tt:{publish_id}",
        )
    return ProviderOutcome(
        kind=ProviderOutcomeKind.ACCEPTED_UNCONFIRMED,
        code=f"tiktok_{status.lower()}",
        retryable=False,
        provider_receipt_ref=f"tt:{publish_id}",
    )


def _creator_info(config: dict) -> dict:
    try:
        response = request_json(
            method="POST",
            url=f"{config['api_base']}/v2/post/publish/creator_info/query/",
            access_token=config["access_token"],
            timeout=config["timeout"],
            payload={},
        )
    except HTTPFailure as exc:
        raise _http_failure(exc, stage="creator_info") from None
    except TransportFailure:
        raise ProviderCallFailure(
            ProviderOutcomeKind.FAILED_RETRYABLE,
            "tiktok_creator_info_transport_failure",
        ) from None
    return _response_data(response, stage="creator_info")


def _response_data(payload: dict, *, stage: str) -> dict:
    error = payload.get("error")
    if isinstance(error, dict):
        code = str(error.get("code") or "").strip()
        if code and code.lower() != "ok":
            kind = (
                ProviderOutcomeKind.FAILED_RETRYABLE
                if code in _RETRYABLE_API_CODES
                else ProviderOutcomeKind.FAILED_FINAL
            )
            raise ProviderCallFailure(kind, f"tiktok_{stage}_rejected")
    data = payload.get("data")
    if not isinstance(data, dict):
        raise ProviderCallFailure(
            ProviderOutcomeKind.FAILED_RETRYABLE,
            f"tiktok_{stage}_response_invalid",
        )
    return data


def _description(artifact) -> str:
    tags = " ".join(f"#{tag}" for tag in artifact.hashtags)
    return "\n\n".join(part for part in (artifact.body, tags) if part)


def _title(value: object) -> str:
    return str(value or "").strip()[:90]


def _public_media_url(value: str) -> bool:
    try:
        parsed = urlsplit(str(value or ""))
    except ValueError:
        return False
    return parsed.scheme.lower() == "https" and bool(parsed.hostname)


def _receipt_id(value: str) -> str:
    text = str(value or "")
    publish_id = text[3:] if text.startswith("tt:") else ""
    return publish_id if _PUBLISH_ID.fullmatch(publish_id) else ""


def _config() -> dict:
    raw = getattr(settings, "SHOPMAN_MARKETING_TIKTOK", {}) or {}
    return {
        "api_base": str(raw.get("api_base") or "https://open.tiktokapis.com").rstrip("/"),
        "access_token": str(raw.get("access_token") or ""),
        "timeout": max(1, int(raw.get("timeout") or 30)),
    }


def _external_allowed() -> bool:
    return not settings.DEBUG or bool(getattr(settings, "SHOPMAN_ALLOW_EXTERNAL_IN_DEBUG", False))


def _not_attempted(code: str) -> None:
    raise ProviderCallFailure(ProviderOutcomeKind.NOT_ATTEMPTED, code)


def _http_failure(exc: HTTPFailure, *, stage: str) -> ProviderCallFailure:
    if exc.status == 429:
        return ProviderCallFailure(
            ProviderOutcomeKind.FAILED_RETRYABLE,
            f"tiktok_{stage}_rate_limited",
            exc.retry_after_seconds,
        )
    if 500 <= exc.status <= 599:
        kind = ProviderOutcomeKind.UNKNOWN if stage == "publish" else ProviderOutcomeKind.FAILED_RETRYABLE
        return ProviderCallFailure(kind, f"tiktok_{stage}_server_failure")
    return ProviderCallFailure(
        ProviderOutcomeKind.FAILED_FINAL,
        f"tiktok_{stage}_rejected",
    )
