"""MKT-20 (beta 05/11): conteúdo público de Marketing nunca sai com link relativo."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from shopman.shop.policies import marketing_public_link
from shopman.shop.services.marketing_contracts import MarketingContractError


@pytest.mark.parametrize(
    "content,platform_content,field",
    [
        ({"body": "Pão", "link": "/produto/KUP"}, None, "content.link"),
        ({"body": "Peça já: /produto/KUP", "link": ""}, None, "content.body"),
        ({"body": "Oferta\n/oferta/fornada-10", "link": ""}, None, "content.body"),
        (
            {"body": "Pão", "link": "https://shop.example/produto/KUP"},
            {"instagram": {"link": "/oferta/fornada-10"}},
            "platform_content.instagram.link",
        ),
    ],
)
def test_relative_store_link_is_a_public_link_problem(content, platform_content, field):
    problem = marketing_public_link.public_link_problem(
        content, platform_content, store_address_configured=False
    )

    assert problem is not None
    assert problem.code == "marketing_link_store_address_missing"
    assert problem.field == field


def test_absolute_store_link_in_link_and_text_passes():
    assert (
        marketing_public_link.public_link_problem(
            {
                "body": "Peça já: https://shop.example/produto/KUP",
                "link": "https://shop.example/produto/KUP",
            },
            {"google_business": {"body": "Veja https://shop.example/oferta/x"}},
            store_address_configured=True,
        )
        is None
    )
    assert (
        marketing_public_link.public_link_problem(
            {"body": "Sem link", "link": ""}, store_address_configured=False
        )
        is None
    )


def test_the_repair_says_what_is_missing():
    without = marketing_public_link.public_link_problem(
        {"link": "/produto/KUP"}, store_address_configured=False
    )
    configured = marketing_public_link.public_link_problem(
        {"link": "/produto/KUP"}, store_address_configured=True
    )

    assert "configurar o endereço do site da loja" in without.repair
    assert "https://" in configured.repair
    for problem in (without, configured):
        assert "—" not in problem.detail + problem.repair
        assert problem.as_payload()["field_detail"] == problem.repair


@pytest.mark.django_db
def test_dispatch_refuses_an_artifact_sealed_with_a_relative_link(settings):
    from shopman.shop.services import marketing_facts

    settings.SHOPMAN_STOREFRONT_BASE_URL = ""
    artifact = SimpleNamespace(payload={"content": {"body": "x", "link": "/produto/KUP"}})

    with pytest.raises(MarketingContractError) as exc:
        marketing_facts.validate_for_dispatch(artifact)

    assert exc.value.code == "marketing_link_store_address_missing"
    assert exc.value.retryable is False
    assert "content.link" in exc.value.field_errors
