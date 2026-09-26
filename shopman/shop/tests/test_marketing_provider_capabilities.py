from __future__ import annotations

import pytest

from shopman.shop.services import (
    marketing_artifacts,
    marketing_capabilities,
    marketing_provider_capabilities,
)
from shopman.shop.services.marketing_contracts import MarketingContractError


def test_provider_catalog_is_complete_without_expanding_the_effect_allow_list():
    assert marketing_provider_capabilities.provider_platform_refs() == (
        "instagram",
        "facebook",
        "google_business",
        "whatsapp",
        "tiktok",
    )
    assert marketing_provider_capabilities.provider_platform_refs(include_dormant=False) == (
        "instagram",
        "facebook",
        "google_business",
        "whatsapp",
    )
    assert set(marketing_capabilities.platform_refs()) == set(
        marketing_provider_capabilities.provider_platform_refs(include_dormant=False)
    )

    with pytest.raises(MarketingContractError) as unknown_platform:
        marketing_artifacts.resolve_dispatch_artifact(
            platform="tiktok",
            content={"body": "Fornada pronta"},
            platform_content={"tiktok": {"publication_format": "photo"}},
            content_version=1,
        )
    assert unknown_platform.value.code == "unknown_platform"


def test_provider_formats_have_unique_stable_identities():
    identities = {
        (provider.platform, format_capability.delivery_kind, format_capability.ref)
        for provider in marketing_provider_capabilities.PROVIDER_CAPABILITIES
        for format_capability in provider.formats
    }

    assert len(identities) == sum(
        len(provider.formats)
        for provider in marketing_provider_capabilities.PROVIDER_CAPABILITIES
    )


def test_instagram_catalog_exposes_provider_media_without_claiming_it_is_ready():
    instagram = marketing_provider_capabilities.provider_capability("instagram")

    assert instagram is not None
    assert instagram.connector_state == "active"
    assert instagram.format("feed").implemented_variants == ("image",)
    assert instagram.format("feed").implementation_state == "partial"
    assert instagram.format("story").implemented_variants == ("image",)
    assert instagram.format("reel").implementation_state == "planned"
    assert instagram.format("carousel").media.max_items == 10
    assert instagram.format("carousel").media.kinds == ("image", "video")


def test_cta_models_preserve_provider_differences():
    instagram = marketing_provider_capabilities.provider_capability("instagram")
    facebook = marketing_provider_capabilities.provider_capability("facebook")
    google = marketing_provider_capabilities.provider_capability("google_business")
    whatsapp = marketing_provider_capabilities.provider_capability("whatsapp")

    assert instagram.format("feed").cta_model == "none"
    assert facebook.format("feed").cta_model == "link"
    assert google.format("standard").cta_model == "provider_choice"
    assert google.format("offer").cta_model == "link"
    assert whatsapp.format("template").cta_model == "template_defined"


def test_google_offer_and_whatsapp_template_keep_their_real_options():
    google = marketing_provider_capabilities.provider_capability("google_business")
    offer_fields = {field.ref for field in google.format("offer").fields}
    assert {"coupon_code", "redeem_online_url", "terms_conditions"} <= offer_fields

    whatsapp = marketing_provider_capabilities.provider_capability("whatsapp")
    assert whatsapp.format("template").implementation_state == "partial"
    assert whatsapp.format("template").media.kinds == ("image", "video", "document")
    assert any("três botões" in note for note in whatsapp.format("template").notes)


def test_tiktok_remains_dormant_but_documents_dynamic_privacy_and_photo_limit():
    tiktok = marketing_provider_capabilities.provider_capability("tiktok")
    photo = tiktok.format("photo")

    assert tiktok.connector_state == "dormant"
    assert photo.implementation_state == "gated"
    assert photo.media.max_items == 35
    privacy = next(field for field in photo.fields if field.ref == "privacy_level")
    assert privacy.required is True
    assert privacy.choices == ()
