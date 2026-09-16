"""Provider-boundary contracts for public Marketing publications."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from threading import Event, Lock
from unittest.mock import Mock
from urllib.error import HTTPError

import pytest
from django.test import override_settings

from shopman.shop.adapters import marketing_delivery_google as google
from shopman.shop.adapters import marketing_delivery_http as http
from shopman.shop.adapters import marketing_delivery_meta as meta
from shopman.shop.adapters import marketing_delivery_tiktok as tiktok
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
GOOGLE_OAUTH = {
    **GOOGLE,
    "access_token": "",
    "client_id": "client-id.apps.googleusercontent.com",
    "client_secret": "secret-client",
    "refresh_token": "secret-refresh",
    "token_url": "https://oauth.example.test/token",
}
TIKTOK = {
    "api_base": "https://open.tiktokapis.example.test",
    "access_token": "secret-tiktok-token",
    "timeout": 9,
}


def artifact(platform: str, publication_format: str, *, image=True):
    return ResolvedDispatchArtifact(
        platform=platform,
        delivery_kind="publication",
        format=publication_format,
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


def test_http_credential_form_has_no_bearer_and_never_places_secrets_in_url(monkeypatch):
    observed = {}

    def open_request(request, *, timeout):
        observed["request"] = request
        observed["timeout"] = timeout
        return _Response(b'{"access_token":"fresh","expires_in":3600}')

    monkeypatch.setattr(http, "_open", open_request)

    result = http.request_form_json(
        url="https://oauth.example.test/token",
        timeout=8,
        payload={"client_secret": "secret-client", "refresh_token": "secret-refresh"},
    )

    request = observed["request"]
    assert result["access_token"] == "fresh"
    assert request.full_url == "https://oauth.example.test/token"
    assert request.get_header("Authorization") is None
    assert b"client_secret=secret-client" in request.data
    assert b"refresh_token=secret-refresh" in request.data
    assert observed["timeout"] == 8


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
    DEBUG=False,
    SHOPMAN_MARKETING_GOOGLE_PUBLICATION_ENABLED=True,
    SHOPMAN_MARKETING_GOOGLE=GOOGLE_OAUTH,
)
def test_google_refreshes_once_and_reuses_short_lived_access_token(monkeypatch):
    refresh = Mock(
        return_value={
            "access_token": "fresh-google-token",
            "expires_in": 3600,
            "token_type": "Bearer",
        }
    )
    request = Mock(
        side_effect=[
            {"name": "accounts/account-1/locations/location-2/localPosts/post-3"},
            {"name": "accounts/account-1/locations/location-2/localPosts/post-3"},
        ]
    )
    google._TOKEN_CACHE.clear()
    monkeypatch.setattr(google, "request_form_json", refresh)
    monkeypatch.setattr(google, "request_json", request)

    sent = google.send(
        artifact=artifact("google_business", "standard"),
        target_key="public",
        idempotency_token="idem",
    )
    google.lookup(
        target_key="public",
        idempotency_token="idem",
        provider_receipt_ref=sent.provider_receipt_ref,
    )

    assert refresh.call_count == 1
    assert refresh.call_args.kwargs["url"] == "https://oauth.example.test/token"
    assert refresh.call_args.kwargs["payload"] == {
        "client_id": "client-id.apps.googleusercontent.com",
        "client_secret": "secret-client",
        "refresh_token": "secret-refresh",
        "grant_type": "refresh_token",
    }
    assert [call.kwargs["access_token"] for call in request.call_args_list] == [
        "fresh-google-token",
        "fresh-google-token",
    ]


def test_google_oauth_refresh_is_single_flight_within_a_worker(monkeypatch):
    config = dict(GOOGLE_OAUTH)
    entered = Event()
    release = Event()
    calls: list[dict] = []
    calls_lock = Lock()

    def refresh(**kwargs):
        with calls_lock:
            calls.append(kwargs)
        entered.set()
        assert release.wait(timeout=2)
        return {
            "access_token": "shared-token",
            "expires_in": 3600,
            "token_type": "Bearer",
        }

    google._TOKEN_CACHE.clear()
    monkeypatch.setattr(google, "request_form_json", refresh)

    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = [executor.submit(google._access_token, config) for _ in range(4)]
        assert entered.wait(timeout=2)
        release.set()
        assert [future.result(timeout=2) for future in futures] == ["shared-token"] * 4

    assert len(calls) == 1


def test_google_oauth_refreshes_again_after_cached_token_expires(monkeypatch):
    config = dict(GOOGLE_OAUTH)
    refresh = Mock(
        side_effect=[
            {"access_token": "token-1", "expires_in": 3600, "token_type": "Bearer"},
            {"access_token": "token-2", "expires_in": 3600, "token_type": "Bearer"},
        ]
    )
    clock = Mock(side_effect=[100.0, 100.0, 3700.0, 3700.0])
    google._TOKEN_CACHE.clear()
    monkeypatch.setattr(google, "request_form_json", refresh)
    monkeypatch.setattr(google.time, "monotonic", clock)

    assert google._access_token(config) == "token-1"
    assert google._access_token(config) == "token-2"
    assert refresh.call_count == 2


@pytest.mark.parametrize(
    ("failure", "expected_kind", "expected_code"),
    [
        (
            HTTPFailure(503),
            ProviderOutcomeKind.FAILED_RETRYABLE,
            "google_oauth_refresh_unavailable",
        ),
        (
            HTTPFailure(400),
            ProviderOutcomeKind.FAILED_FINAL,
            "google_oauth_refresh_rejected",
        ),
        (
            TransportFailure(),
            ProviderOutcomeKind.FAILED_RETRYABLE,
            "google_oauth_refresh_unavailable",
        ),
    ],
)
@override_settings(
    DEBUG=False,
    SHOPMAN_MARKETING_GOOGLE_PUBLICATION_ENABLED=True,
    SHOPMAN_MARKETING_GOOGLE=GOOGLE_OAUTH,
)
def test_google_oauth_refresh_failures_are_sanitized_and_never_publish(
    monkeypatch,
    failure,
    expected_kind,
    expected_code,
):
    google._TOKEN_CACHE.clear()
    publish = Mock()
    monkeypatch.setattr(google, "request_form_json", Mock(side_effect=failure))
    monkeypatch.setattr(google, "request_json", publish)

    with pytest.raises(ProviderCallFailure) as caught:
        google.send(
            artifact=artifact("google_business", "standard"),
            target_key="public",
            idempotency_token="idem",
        )

    assert caught.value.kind == expected_kind
    assert caught.value.code == expected_code
    assert "secret-client" not in str(caught.value)
    assert "secret-refresh" not in str(caught.value)
    assert publish.call_count == 0


@override_settings(
    DEBUG=False,
    SHOPMAN_MARKETING_GOOGLE_PUBLICATION_ENABLED=True,
    SHOPMAN_MARKETING_GOOGLE=GOOGLE_OAUTH,
)
def test_google_rejects_malformed_oauth_response_without_publishing(monkeypatch):
    google._TOKEN_CACHE.clear()
    publish = Mock()
    monkeypatch.setattr(
        google,
        "request_form_json",
        Mock(return_value={"access_token": "", "token_type": "Bearer"}),
    )
    monkeypatch.setattr(google, "request_json", publish)

    with pytest.raises(ProviderCallFailure) as caught:
        google.send(
            artifact=artifact("google_business", "standard"),
            target_key="public",
            idempotency_token="idem",
        )

    assert caught.value.kind == ProviderOutcomeKind.FAILED_FINAL
    assert caught.value.code == "google_oauth_refresh_response_invalid"
    assert publish.call_count == 0


@override_settings(
    DEBUG=False,
    SHOPMAN_MARKETING_GOOGLE_PUBLICATION_ENABLED=True,
    SHOPMAN_MARKETING_GOOGLE=GOOGLE_OAUTH,
)
def test_google_rejected_cached_oauth_token_is_invalidated_and_retried_later(monkeypatch):
    google._TOKEN_CACHE.clear()
    refresh = Mock(
        side_effect=[
            {"access_token": "stale-token", "expires_in": 3600, "token_type": "Bearer"},
            {"access_token": "fresh-token", "expires_in": 3600, "token_type": "Bearer"},
        ]
    )
    publish = Mock(
        side_effect=[
            HTTPFailure(401),
            {"name": "accounts/account-1/locations/location-2/localPosts/post-4"},
        ]
    )
    monkeypatch.setattr(google, "request_form_json", refresh)
    monkeypatch.setattr(google, "request_json", publish)

    with pytest.raises(ProviderCallFailure) as caught:
        google.send(
            artifact=artifact("google_business", "standard"),
            target_key="public",
            idempotency_token="idem-1",
        )

    assert caught.value.kind == ProviderOutcomeKind.FAILED_RETRYABLE
    assert caught.value.code == "google_publish_oauth_token_rejected"
    assert google._TOKEN_CACHE == {}

    outcome = google.send(
        artifact=artifact("google_business", "standard"),
        target_key="public",
        idempotency_token="idem-2",
    )

    assert outcome.provider_receipt_ref == "gbp:post-4"
    assert refresh.call_count == 2
    assert [call.kwargs["access_token"] for call in publish.call_args_list] == [
        "stale-token",
        "fresh-token",
    ]


@override_settings(
    DEBUG=False,
    SHOPMAN_MARKETING_GOOGLE_PUBLICATION_ENABLED=True,
    SHOPMAN_MARKETING_GOOGLE=GOOGLE,
)
def test_google_static_token_rejection_remains_final(monkeypatch):
    monkeypatch.setattr(google, "request_json", Mock(side_effect=HTTPFailure(401)))

    with pytest.raises(ProviderCallFailure) as caught:
        google.send(
            artifact=artifact("google_business", "standard"),
            target_key="public",
            idempotency_token="idem",
        )

    assert caught.value.kind == ProviderOutcomeKind.FAILED_FINAL
    assert caught.value.code == "google_publish_rejected"


@override_settings(
    DEBUG=False,
    SHOPMAN_MARKETING_GOOGLE_PUBLICATION_ENABLED=True,
    SHOPMAN_MARKETING_GOOGLE={
        **GOOGLE_OAUTH,
        "access_token": "legacy-static-token",
        "client_secret": "",
    },
)
def test_google_partial_oauth_configuration_remains_unavailable():
    assert google.is_available() is False


@override_settings(
    DEBUG=False,
    SHOPMAN_MARKETING_GOOGLE_PUBLICATION_ENABLED=True,
    SHOPMAN_MARKETING_GOOGLE={
        **GOOGLE_OAUTH,
        "access_token": "legacy-static-token",
        "token_url": "http://oauth.example.test/token",
    },
)
def test_google_insecure_oauth_endpoint_remains_unavailable():
    assert google.is_available() is False


@override_settings(
    DEBUG=True,
    SHOPMAN_ALLOW_EXTERNAL_IN_DEBUG=False,
    SHOPMAN_MARKETING_INSTAGRAM_PUBLICATION_ENABLED=True,
    SHOPMAN_MARKETING_META=META,
)
def test_external_publication_is_closed_in_debug_without_independent_opt_in():
    assert meta.instagram_available() is False


@override_settings(
    DEBUG=False,
    SHOPMAN_MARKETING_TIKTOK_PUBLICATION_ENABLED=True,
    SHOPMAN_MARKETING_TIKTOK=TIKTOK,
)
def test_tiktok_photo_direct_post_queries_creator_and_preserves_explicit_choices(
    monkeypatch,
):
    request = Mock(
        side_effect=[
            {
                "data": {
                    "privacy_level_options": ["PUBLIC_TO_EVERYONE", "SELF_ONLY"],
                    "comment_disabled": False,
                },
                "error": {"code": "ok"},
            },
            {
                "data": {"publish_id": "publish-v2-1"},
                "error": {"code": "ok"},
            },
        ]
    )
    monkeypatch.setattr(tiktok, "request_json", request)
    photo = ResolvedDispatchArtifact(
        platform="tiktok",
        delivery_kind="publication",
        format="photo",
        body="Lá vem a primavera...",
        hashtags=("primavera",),
        image_url="https://cdn.example.test/hibisco.jpg",
        provider_fields=(
            ("title", "Primavera"),
            ("privacy_level", "PUBLIC_TO_EVERYONE"),
            ("disable_comment", False),
            ("auto_add_music", False),
            ("commercial_content", True),
            ("brand_organic_toggle", True),
            ("brand_content_toggle", False),
            ("consent_confirmed", True),
        ),
    )

    outcome = tiktok.send(
        artifact=photo,
        target_key="public",
        idempotency_token="idem",
    )

    assert outcome.kind == ProviderOutcomeKind.ACCEPTED_UNCONFIRMED
    assert outcome.provider_receipt_ref == "tt:publish-v2-1"
    assert request.call_args_list[0].kwargs["url"].endswith("/v2/post/publish/creator_info/query/")
    publish = request.call_args_list[1].kwargs
    assert publish["payload"] == {
        "post_info": {
            "title": "Primavera",
            "description": "Lá vem a primavera...\n\n#primavera",
            "disable_comment": False,
            "privacy_level": "PUBLIC_TO_EVERYONE",
            "auto_add_music": False,
            "brand_content_toggle": False,
            "brand_organic_toggle": True,
        },
        "source_info": {
            "source": "PULL_FROM_URL",
            "photo_cover_index": 0,
            "photo_images": ["https://cdn.example.test/hibisco.jpg"],
        },
        "post_mode": "DIRECT_POST",
        "media_type": "PHOTO",
    }
    assert "secret-tiktok-token" not in publish["url"]


@override_settings(
    DEBUG=False,
    SHOPMAN_MARKETING_TIKTOK_PUBLICATION_ENABLED=True,
    SHOPMAN_MARKETING_TIKTOK=TIKTOK,
)
def test_tiktok_never_invents_required_operator_choices(monkeypatch):
    request = Mock()
    monkeypatch.setattr(tiktok, "request_json", request)

    with pytest.raises(ProviderCallFailure) as caught:
        tiktok.send(
            artifact=ResolvedDispatchArtifact(
                platform="tiktok",
                delivery_kind="publication",
                format="photo",
                body="Sem escolhas explícitas",
                image_url="https://cdn.example.test/hibisco.jpg",
            ),
            target_key="public",
            idempotency_token="idem",
        )

    assert caught.value.kind == ProviderOutcomeKind.NOT_ATTEMPTED
    assert request.call_count == 0


@override_settings(
    DEBUG=False,
    SHOPMAN_MARKETING_TIKTOK_PUBLICATION_ENABLED=True,
    SHOPMAN_MARKETING_TIKTOK=TIKTOK,
)
def test_tiktok_lost_publish_response_is_unknown_and_not_retried(monkeypatch):
    request = Mock(
        side_effect=[
            {
                "data": {
                    "privacy_level_options": ["SELF_ONLY"],
                    "comment_disabled": False,
                },
                "error": {"code": "ok"},
            },
            TransportFailure(),
        ]
    )
    monkeypatch.setattr(tiktok, "request_json", request)
    photo = ResolvedDispatchArtifact(
        platform="tiktok",
        delivery_kind="publication",
        format="photo",
        body="Teste privado",
        image_url="https://cdn.example.test/hibisco.jpg",
        provider_fields=(
            ("privacy_level", "SELF_ONLY"),
            ("disable_comment", False),
            ("auto_add_music", False),
            ("commercial_content", False),
            ("brand_organic_toggle", False),
            ("brand_content_toggle", False),
            ("consent_confirmed", True),
        ),
    )

    with pytest.raises(ProviderCallFailure) as caught:
        tiktok.send(
            artifact=photo,
            target_key="public",
            idempotency_token="idem",
        )

    assert caught.value.kind == ProviderOutcomeKind.UNKNOWN
    assert request.call_count == 2


@override_settings(
    DEBUG=True,
    SHOPMAN_ALLOW_EXTERNAL_IN_DEBUG=False,
    SHOPMAN_MARKETING_TIKTOK_PUBLICATION_ENABLED=True,
    SHOPMAN_MARKETING_TIKTOK=TIKTOK,
)
def test_tiktok_is_closed_in_debug_without_independent_external_opt_in():
    assert tiktok.is_available() is False
