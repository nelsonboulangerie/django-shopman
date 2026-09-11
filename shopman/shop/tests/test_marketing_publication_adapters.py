"""Provider-boundary contracts for public Marketing publications."""

from __future__ import annotations

from io import BytesIO
from unittest.mock import Mock
from urllib.error import HTTPError

import pytest
from django.test import override_settings

from shopman.shop.adapters import marketing_delivery_google as google
from shopman.shop.adapters import marketing_delivery_http as http
from shopman.shop.adapters import marketing_delivery_meta as meta
from shopman.shop.adapters.marketing_delivery_http import HTTPFailure, TransportFailure
from shopman.shop.services.marketing_contracts import (
    ProviderCallFailure,
    ProviderOutcomeKind,
    ResolvedDispatchArtifact,
)

META = {
    "api_base": "https://graph.example.test",
    "api_version": "v99.0",
    "ig_user_id": "ig-123",
    "page_id": "page-456",
    "page_access_token": "secret-meta-token",
    "timeout": 7,
}
GOOGLE = {
    "api_base": "https://business.example.test",
    "api_version": "v4",
    "account_id": "account-1",
    "location_id": "location-2",
    "access_token": "secret-google-token",
    "timeout": 8,
}


def artifact(platform: str, publication_format: str, *, image=True):
    return ResolvedDispatchArtifact(
        platform=platform,
        body="Madeleines quentinhas",
        hashtags=("fornada",),
        link="https://loja.example.test/produto/mad",
        image_url="https://cdn.example.test/story.jpg" if image else "",
        provider_fields=(("publication_format", publication_format),),
    )


class _Response:
    def __init__(self, payload: bytes):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def read(self, _limit=None):
        return self.payload


def test_http_boundary_keeps_token_out_of_url_and_normalizes_form_boole(monkeypatch):
    observed = {}

    def open_request(request, *, timeout):
        observed["request"] = request
        observed["timeout"] = timeout
        return _Response(b'{"id":"accepted-1"}')

    monkeypatch.setattr(http, "_open", open_request)

    result = http.request_json(
        method="POST",
        url="https://graph.example.test/v99/page/photos",
        access_token="secret-meta-token",
        timeout=7,
        payload={"published": True, "caption": "Fornada pronta"},
        encoding="form",
    )

    request = observed["request"]
    assert result == {"id": "accepted-1"}
    assert request.full_url == "https://graph.example.test/v99/page/photos"
    assert request.get_header("Authorization") == "Bearer secret-meta-token"
    assert b"published=true" in request.data
    assert observed["timeout"] == 7


def test_http_boundary_never_propagates_provider_response_body(monkeypatch):
    def reject(_request, *, timeout):
        del timeout
        raise HTTPError(
            "https://graph.example.test/v99/page/photos",
            400,
            "bad request",
            {},
            BytesIO(b"secret-meta-token and customer content"),
        )

    monkeypatch.setattr(http, "_open", reject)

    with pytest.raises(HTTPFailure) as caught:
        http.request_json(
            method="POST",
            url="https://graph.example.test/v99/page/photos",
            access_token="secret-meta-token",
            timeout=7,
            payload={"caption": "customer content"},
            encoding="form",
        )

    assert caught.value.status == 400
    assert "secret-meta-token" not in str(caught.value)
    assert "customer content" not in str(caught.value)


def test_http_boundary_refuses_redirect_before_bearer_can_move_hosts():
    handler = http._NoRedirect()

    redirected = handler.redirect_request(
        Mock(),
        None,
        302,
        "moved",
        {},
        "https://unexpected.example.test/collect",
    )

    assert redirected is None


def test_http_boundary_rejects_oversized_provider_response(monkeypatch):
    monkeypatch.setattr(
        http,
        "_open",
        lambda _request, *, timeout: _Response(
            b"{" + b'\"padding\":\"' + (b"x" * http.MAX_RESPONSE_BYTES) + b'\"}'
        ),
    )

    with pytest.raises(TransportFailure):
        http.request_json(
            method="GET",
            url="https://graph.example.test/v99/page",
            access_token="secret-meta-token",
            timeout=7,
        )


@override_settings(
    DEBUG=False,
    SHOPMAN_MARKETING_INSTAGRAM_PUBLICATION_ENABLED=True,
    SHOPMAN_MARKETING_META=META,
)
def test_instagram_story_creates_story_then_publishes_without_fake_caption(monkeypatch):
    request = Mock(side_effect=[{"id": "container-1"}, {"id": "media-2"}])
    monkeypatch.setattr(meta, "request_json", request)

    outcome = meta.send_instagram(
        artifact=artifact("instagram", "story"),
        target_key="public",
        idempotency_token="idem",
    )

    assert outcome.kind == ProviderOutcomeKind.ACCEPTED_UNCONFIRMED
    assert outcome.provider_receipt_ref == "ig:media-2"
    prepare = request.call_args_list[0].kwargs
    publish = request.call_args_list[1].kwargs
    assert prepare["payload"] == {
        "image_url": "https://cdn.example.test/story.jpg",
        "media_type": "STORIES",
    }
    assert publish["payload"] == {"creation_id": "container-1"}
    assert "secret-meta-token" not in prepare["url"]


@override_settings(
    DEBUG=False,
    SHOPMAN_MARKETING_INSTAGRAM_PUBLICATION_ENABLED=True,
    SHOPMAN_MARKETING_META=META,
)
def test_instagram_feed_is_only_used_when_explicit(monkeypatch):
    request = Mock(side_effect=[{"id": "container-1"}, {"id": "media-2"}])
    monkeypatch.setattr(meta, "request_json", request)

    meta.send_instagram(
        artifact=artifact("instagram", "feed"),
        target_key="public",
        idempotency_token="idem",
    )

    assert request.call_args_list[0].kwargs["payload"]["caption"].startswith(
        "Madeleines quentinhas"
    )
    assert "media_type" not in request.call_args_list[0].kwargs["payload"]


@override_settings(
    DEBUG=False,
    SHOPMAN_MARKETING_INSTAGRAM_PUBLICATION_ENABLED=True,
    SHOPMAN_MARKETING_META=META,
)
def test_old_instagram_artifact_never_silently_falls_back(monkeypatch):
    request = Mock()
    monkeypatch.setattr(meta, "request_json", request)
    old = ResolvedDispatchArtifact(
        platform="instagram",
        body="Antes da decisão de formato",
        image_url="https://cdn.example.test/story.jpg",
    )

    with pytest.raises(ProviderCallFailure) as caught:
        meta.send_instagram(artifact=old, target_key="public", idempotency_token="idem")

    assert caught.value.kind == ProviderOutcomeKind.NOT_ATTEMPTED
    assert request.call_count == 0


@override_settings(
    DEBUG=False,
    SHOPMAN_MARKETING_INSTAGRAM_PUBLICATION_ENABLED=True,
    SHOPMAN_MARKETING_META=META,
)
def test_instagram_lost_publish_response_is_unknown_and_not_retryable(monkeypatch):
    request = Mock(side_effect=[{"id": "container-1"}, TransportFailure()])
    monkeypatch.setattr(meta, "request_json", request)

    with pytest.raises(ProviderCallFailure) as caught:
        meta.send_instagram(
            artifact=artifact("instagram", "story"),
            target_key="public",
            idempotency_token="idem",
        )

    assert caught.value.kind == ProviderOutcomeKind.UNKNOWN


@override_settings(
    DEBUG=False,
    SHOPMAN_MARKETING_INSTAGRAM_PUBLICATION_ENABLED=True,
    SHOPMAN_MARKETING_META=META,
)
def test_instagram_prepare_rate_limit_is_safe_to_retry(monkeypatch):
    monkeypatch.setattr(
        meta,
        "request_json",
        Mock(side_effect=HTTPFailure(429, retry_after_seconds=12)),
    )

    with pytest.raises(ProviderCallFailure) as caught:
        meta.send_instagram(
            artifact=artifact("instagram", "story"),
            target_key="public",
            idempotency_token="idem",
        )

    assert caught.value.kind == ProviderOutcomeKind.FAILED_RETRYABLE
    assert caught.value.retry_after_seconds == 12


@override_settings(
    DEBUG=False,
    SHOPMAN_MARKETING_FACEBOOK_PUBLICATION_ENABLED=True,
    SHOPMAN_MARKETING_META=META,
)
def test_facebook_photo_publication_and_lookup(monkeypatch):
    request = Mock(side_effect=[{"post_id": "page-456_9"}, {"id": "page-456_9"}])
    monkeypatch.setattr(meta, "request_json", request)

    sent = meta.send_facebook(
        artifact=artifact("facebook", "feed"),
        target_key="public",
        idempotency_token="idem",
    )
    confirmed = meta.lookup_facebook(
        target_key="public",
        idempotency_token="idem",
        provider_receipt_ref=sent.provider_receipt_ref,
    )

    assert sent.provider_receipt_ref == "fb:page-456_9"
    assert request.call_args_list[0].kwargs["url"].endswith("/page-456/photos")
    assert confirmed.kind == ProviderOutcomeKind.CONFIRMED


@override_settings(
    DEBUG=False,
    SHOPMAN_MARKETING_GOOGLE_PUBLICATION_ENABLED=True,
    SHOPMAN_MARKETING_GOOGLE=GOOGLE,
)
def test_google_standard_post_and_lookup(monkeypatch):
    request = Mock(
        side_effect=[
            {"name": "accounts/account-1/locations/location-2/localPosts/post-3"},
            {"name": "accounts/account-1/locations/location-2/localPosts/post-3"},
        ]
    )
    monkeypatch.setattr(google, "request_json", request)

    sent = google.send(
        artifact=artifact("google_business", "standard"),
        target_key="public",
        idempotency_token="idem",
    )
    confirmed = google.lookup(
        target_key="public",
        idempotency_token="idem",
        provider_receipt_ref=sent.provider_receipt_ref,
    )

    payload = request.call_args_list[0].kwargs["payload"]
    assert payload["topicType"] == "STANDARD"
    assert payload["callToAction"]["actionType"] == "ORDER"
    assert sent.provider_receipt_ref == "gbp:post-3"
    assert confirmed.kind == ProviderOutcomeKind.CONFIRMED
    assert "secret-google-token" not in request.call_args_list[0].kwargs["url"]


@override_settings(
    DEBUG=True,
    SHOPMAN_ALLOW_EXTERNAL_IN_DEBUG=False,
    SHOPMAN_MARKETING_INSTAGRAM_PUBLICATION_ENABLED=True,
    SHOPMAN_MARKETING_META=META,
)
def test_external_publication_is_closed_in_debug_without_independent_opt_in():
    assert meta.instagram_available() is False
