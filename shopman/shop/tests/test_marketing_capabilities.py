from __future__ import annotations

import pytest

from shopman.shop.services import marketing_artifacts, marketing_capabilities
from shopman.shop.services.marketing_contracts import MarketingContractError


def test_catalog_has_unique_complete_destination_identities():
    identities = {
        (destination.platform, destination.delivery_kind, format_.ref)
        for destination in marketing_capabilities.DESTINATIONS
        for format_ in destination.formats
    }

    assert len(identities) == sum(
        len(destination.formats)
        for destination in marketing_capabilities.DESTINATIONS
    )
    assert marketing_capabilities.platform_refs() == (
        "instagram",
        "facebook",
        "google_business",
        "whatsapp",
    )
    assert marketing_capabilities.publication_platform_refs() == (
        "instagram",
        "facebook",
        "google_business",
    )


def test_every_default_format_belongs_to_its_destination():
    for destination in marketing_capabilities.DESTINATIONS:
        assert destination.format(destination.default_format) is not None


def test_new_content_rejects_a_provider_option_with_no_effect():
    with pytest.raises(MarketingContractError) as caught:
        marketing_artifacts.normalize_platform_content(
            platforms=("instagram",),
            platform_content={
                "instagram": {
                    "publication_format": "story",
                    "sticker_link": "https://example.com/item",
                }
            },
        )

    assert caught.value.code == "unsupported_provider_field"
    assert (
        "platform_content.instagram.sticker_link" in caught.value.field_errors
    )


def test_closed_schema_keeps_content_fields_and_supported_whatsapp_metadata():
    normalized = marketing_artifacts.normalize_platform_content(
        platforms=("whatsapp",),
        platform_content={
            "whatsapp": {
                "body": "Fornada pronta",
                "image_url": "https://example.com/foto.jpg",
                "template_name": "fornada",
            }
        },
    )

    assert normalized == {
        "whatsapp": {
            "body": "Fornada pronta",
            "image_url": "https://example.com/foto.jpg",
            "template_name": "fornada",
        }
    }


def test_publication_defaults_still_come_from_the_catalog():
    normalized = marketing_artifacts.normalize_platform_content(
        platforms=("instagram", "facebook", "google_business"),
        platform_content={},
    )

    assert normalized == {
        "instagram": {"publication_format": "story"},
        "facebook": {"publication_format": "feed"},
        "google_business": {"publication_format": "standard"},
    }
