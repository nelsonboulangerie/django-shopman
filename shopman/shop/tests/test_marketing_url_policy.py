"""MKT-031 — URL/media threat controls at preview, browser and provider edges."""

from __future__ import annotations

import socket
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from django.test import override_settings

from shopman.shop.handlers import campaign as handlers
from shopman.shop.models import Announcement, AnnouncementStatus
from shopman.shop.services import marketing_url_policy
from shopman.shop.services.marketing_artifacts import resolve_dispatch_artifact
from shopman.shop.services.marketing_contracts import MarketingContractError

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def trusted_origins(settings):
    settings.SHOPMAN_STOREFRONT_BASE_URL = "https://shop.example"
    settings.SHOPMAN_MARKETING_MEDIA_HOSTS = ("cdn.example",)


@pytest.mark.parametrize(
    "url",
    [
        "/produto/CRO-001",
        "/oferta/fornada-10",
        "https://shop.example/produto/CRO-001",
        "https://shop.example/oferta/fornada-10",
    ],
)
def test_only_canonical_same_store_customer_destinations_are_accepted(url):
    assert marketing_url_policy.validate_customer_link(url) == url


@pytest.mark.parametrize(
    ("url", "code"),
    [
        ("http://shop.example/produto/CRO-001", "marketing_link_https_required"),
        ("https://shop.example.evil/produto/CRO-001", "marketing_link_host_not_allowed"),
        ("https://user@shop.example/produto/CRO-001", "marketing_link_userinfo_forbidden"),
        ("https://shop.example:8443/produto/CRO-001", "marketing_link_port_forbidden"),
        ("https://shop.example/produto/CRO-001?utm_source=x", "marketing_link_tracking_forbidden"),
        ("https://shop.example/produto/CRO-001#x", "marketing_link_tracking_forbidden"),
        ("https://shop.example/redirect/CRO-001", "marketing_link_path_not_canonical"),
        ("//shop.example/produto/CRO-001", "marketing_link_invalid"),
        ("https://shop.example/produto/%2e%2e", "marketing_link_path_not_canonical"),
    ],
)
def test_external_redirect_and_tracking_link_shapes_fail_closed(url, code):
    with pytest.raises(MarketingContractError) as caught:
        marketing_url_policy.validate_customer_link(url)

    assert caught.value.code == code
    assert caught.value.field_errors == {
        "content.link": ("Use o destino canônico da loja.",)
    }


def test_trusted_media_allows_only_bounded_image_transform_parameters():
    url = "https://cdn.example/img/croissant.jpg?auto=format&fit=crop&w=900&q=80"

    assert marketing_url_policy.validate_media_url(url) == url


@pytest.mark.parametrize(
    ("url", "code"),
    [
        ("http://cdn.example/img/x.jpg", "marketing_media_https_required"),
        ("https://cdn.example.evil/img/x.jpg", "marketing_media_host_not_allowed"),
        ("https://127.0.0.1/img/x.jpg", "marketing_media_private_host"),
        ("https://169.254.169.254/latest/meta-data", "marketing_media_private_host"),
        ("https://[::1]/img/x.jpg", "marketing_media_private_host"),
        ("https://localhost/img/x.jpg", "marketing_media_private_host"),
        ("https://user@cdn.example/img/x.jpg", "marketing_media_userinfo_forbidden"),
        ("https://cdn.example:444/img/x.jpg", "marketing_media_port_forbidden"),
        ("https://cdn.example/img/x.jpg#pixel", "marketing_media_fragment_forbidden"),
        ("https://cdn.example/img/x.jpg?utm_source=operator", "marketing_media_tracking_query"),
        ("https://cdn.example/redirect?url=http://127.0.0.1", "marketing_media_tracking_query"),
        ("https://cdn.example/img/%2e%2e/secret", "marketing_media_path_invalid"),
    ],
)
def test_media_private_redirect_tracking_and_credential_shapes_fail_closed(url, code):
    with pytest.raises(MarketingContractError) as caught:
        marketing_url_policy.validate_media_url(url)

    assert caught.value.code == code


def test_redirect_policy_never_allows_a_second_origin():
    with pytest.raises(MarketingContractError) as caught:
        marketing_url_policy.validate_media_redirect(
            "https://cdn.example/img/x.jpg",
            "https://shop.example/media/x.jpg",
        )

    assert caught.value.code == "marketing_media_redirect_forbidden"


def test_validation_does_not_resolve_dns_or_fetch_untrusted_content(monkeypatch):
    def explode(*args, **kwargs):
        raise AssertionError("URL validation crossed the network boundary")

    monkeypatch.setattr(socket, "getaddrinfo", explode)

    with pytest.raises(MarketingContractError):
        marketing_url_policy.validate_media_url("https://attacker.example/pixel")


def test_artifact_points_to_the_exact_variant_field_that_needs_repair():
    with pytest.raises(MarketingContractError) as caught:
        resolve_dispatch_artifact(
            platform="instagram",
            content={"body": "Fornada pronta", "image_url": "/media/safe.jpg"},
            platform_content={
                "instagram": {"image_url": "https://169.254.169.254/token"}
            },
            content_version=1,
        )

    assert caught.value.code == "marketing_media_private_host"
    assert "platform_content.instagram.image_url" in caught.value.field_errors


def test_operator_projection_never_makes_the_browser_fetch_an_untrusted_image():
    from shopman.backstage.projections.marketing import build_announcement

    announcement = Announcement.objects.create(
        status=AnnouncementStatus.PENDING_REVIEW,
        content={
            "body": "Fornada pronta",
            "image_url": "https://attacker.example/operator-pixel",
            "link": "https://attacker.example/redirect",
        },
        platforms=["instagram"],
    )

    projected = build_announcement(announcement)

    assert projected.image_url == ""
    assert projected.link == ""


def test_legacy_posting_boundary_blocks_before_the_provider_call():
    announcement = Announcement.objects.create(
        status=AnnouncementStatus.PUBLISHING,
        content={
            "body": "Fornada pronta",
            "image_url": "https://169.254.169.254/token",
            "link": "/produto/CRO-001",
        },
        platforms=["instagram"],
    )
    adapter = MagicMock()
    message = SimpleNamespace(
        pk=1,
        payload={"announcement_id": announcement.pk, "platform": "instagram"},
    )

    with patch.object(handlers, "_posting_adapter", return_value=adapter):
        handlers.AnnouncementHandler().handle(message=message, ctx={})

    adapter.publish.assert_not_called()
    announcement.refresh_from_db()
    assert announcement.platform_results["instagram"] == {
        "status": "failed",
        "reason": "marketing_media_private_host",
    }


@override_settings(SHOPMAN_MARKETING_MEDIA_HOSTS=("cdn.example", "127.0.0.1"))
def test_private_literal_never_becomes_trusted_even_if_misconfigured():
    assert "127.0.0.1" in marketing_url_policy.invalid_trusted_media_hosts()
    with pytest.raises(MarketingContractError) as caught:
        marketing_url_policy.validate_media_url("https://127.0.0.1/image.jpg")
    assert caught.value.code == "marketing_media_private_host"
