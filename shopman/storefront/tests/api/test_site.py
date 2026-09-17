"""GET /api/v1/storefront/site/ — busca, cartão de link, dados do negócio e FAQ."""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.contrib import admin
from django.test import Client
from django.urls import reverse

from shopman.shop.models import Channel, FAQEntry, Shop
from shopman.storefront.presentation.product_detail import _seo_description
from shopman.storefront.presentation.site import build_opening_hours

pytestmark = pytest.mark.django_db


def _shop(**overrides) -> Shop:
    Channel.objects.get_or_create(ref="web", defaults={"name": "Loja Online"})
    values = {
        "name": "Padaria Teste",
        "brand_name": "Padaria Teste",
        "tagline": "Padaria Artesanal",
        "description": "Pães de fermentação natural.",
        "city": "Londrina",
        "state_code": "PR",
        "route": "Av. Madre Leônia Milito",
        "street_number": "446",
        "neighborhood": "Bela Suíça",
        "postal_code": "86050-270",
        "latitude": Decimal("-23.3348384"),
        "longitude": Decimal("-51.1673157"),
        "phone": "554333231997",
        "email": "ola@padaria.test",
        "social_links": [
            "https://wa.me/554333231997",
            "https://www.instagram.com/padariateste",
            "https://www.facebook.com/padariateste",
        ],
        "opening_hours": {
            "monday": {"open": "09:00", "close": "18:00"},
            "tuesday": {"open": "09:00", "close": "18:00"},
            "saturday": {"open": "08:00", "close": "13:00"},
        },
    }
    values.update(overrides)
    return Shop.objects.create(**values)


def _site(client) -> dict:
    response = client.get("/api/v1/storefront/site/")
    assert response.status_code == 200
    return response.json()["site"]


def test_empty_search_fields_fall_back_to_what_the_brand_already_says(client):
    _shop()

    pages = _site(client)["pages"]

    assert pages["home"] == {
        "title": "Padaria Teste · Padaria Artesanal em Londrina",
        "description": "Pães de fermentação natural.",
    }
    assert pages["menu"]["title"] == "Cardápio"
    assert "Padaria Teste em Londrina" in pages["menu"]["description"]
    assert pages["faq"]["title"] == "Perguntas frequentes"
    assert pages["faq"]["description"]


def test_what_the_manager_writes_in_admin_wins_over_the_derived_text(client):
    _shop(
        seo_home_title="Título escrito",
        seo_home_description="Descrição escrita.",
        seo_menu_description="Cardápio escrito.",
        seo_faq_description="FAQ escrita.",
        seo_share_image_url="https://cdn.test/cartao.jpg",
        google_site_verification="g-code",
        bing_site_verification="b-code",
        facebook_domain_verification="f-code",
        pinterest_domain_verification="p-code",
    )

    site = _site(client)

    assert site["pages"]["home"] == {"title": "Título escrito", "description": "Descrição escrita."}
    assert site["pages"]["menu"]["description"] == "Cardápio escrito."
    assert site["pages"]["faq"]["description"] == "FAQ escrita."
    assert site["share_image_url"] == "https://cdn.test/cartao.jpg"
    assert site["verifications"] == {
        "google": "g-code",
        "bing": "b-code",
        "facebook": "f-code",
        "pinterest": "p-code",
    }


def test_business_carries_structured_address_hours_and_brand_profiles(client):
    _shop(price_range="$$", founding_year=1997)

    business = _site(client)["business"]

    assert business["type"] == "Bakery"
    assert business["telephone"] == "+554333231997"
    assert business["price_range"] == "$$"
    assert business["founding_year"] == 1997
    assert business["address"] == {
        "street": "Av. Madre Leônia Milito, 446",
        "neighborhood": "Bela Suíça",
        "locality": "Londrina",
        "region": "PR",
        "postal_code": "86050-270",
        "country_code": "BR",
    }
    assert business["geo"] == {"latitude": -23.3348384, "longitude": -51.1673157}
    assert business["opening_hours"] == [
        {"days": ["Monday", "Tuesday"], "opens": "09:00", "closes": "18:00"},
        {"days": ["Saturday"], "opens": "08:00", "closes": "13:00"},
    ]
    assert business["maps_url"]
    # WhatsApp é canal de conversa, não perfil da marca: fora do sameAs.
    assert business["same_as"] == [
        "https://www.instagram.com/padariateste",
        "https://www.facebook.com/padariateste",
    ]


def test_business_without_coordinates_says_nothing_about_geo(client):
    _shop(latitude=None, longitude=None)

    assert _site(client)["business"]["geo"] is None


def test_only_published_curated_answers_join_the_operational_faq(client):
    _shop()
    FAQEntry.objects.create(question="Vocês usam fermento natural?", answer="Sim, levain.", is_published=True)
    FAQEntry.objects.create(question="Rascunho?", answer="Ainda não.", is_published=False)

    questions = [item["question"] for item in _site(client)["faq"]]

    assert "Vocês usam fermento natural?" in questions
    assert "Rascunho?" not in questions


def test_without_a_shop_there_is_no_site(client):
    assert client.get("/api/v1/storefront/site/").status_code == 404


def test_opening_hours_skip_closed_and_half_filled_days():
    assert build_opening_hours({
        "sunday": {"open": "", "close": ""},
        "monday": {"open": "07:00"},
        "friday": {"open": "07:00", "close": "19:00"},
    }) == (
        build_opening_hours({"friday": {"open": "07:00", "close": "19:00"}})
    )
    assert build_opening_hours(None) == ()


def test_product_search_description_ends_the_catalog_sentence_before_the_allergens():
    product = SimpleNamespace(
        short_description="Pão de tradição francesa e fermentação 100% natural (levain)",
        long_description="",
        name="Pão",
    )
    allergen = SimpleNamespace(allergens=("glúten",), dietary_info=())

    description = _seo_description(product, allergen=allergen, conservation=None)

    assert description == (
        "Pão de tradição francesa e fermentação 100% natural (levain). Atenção a alergias: glúten."
    )


def test_search_settings_have_their_own_admin_page(admin_user):
    from shopman.shop.models import ShopSearch

    shop = _shop()
    assert ShopSearch in admin.site._registry
    client = Client()
    client.force_login(admin_user)

    response = client.get(reverse("admin:shop_shopsearch_change", args=[shop.pk]))

    assert response.status_code == 200
    content = response.content.decode()
    for field in ("seo_home_title", "price_range", "facebook_domain_verification"):
        assert f'name="{field}"' in content
    # A página é focada: o horário continua na sua própria tela.
    assert 'name="opening_hours_monday_status"' not in content


# ── apply_search_presence: o alpha recebe o que um banco novo nasce tendo ──


def test_apply_search_presence_fills_only_what_is_missing():
    from config.management.commands.apply_search_presence import PUBLIC_FAQ, apply_search_presence

    shop = _shop(
        seo_home_title="O gestor já escreveu",
        social_links=["https://wa.me/554333231997", "https://instagram.com/example", "http://instagram.com/nelsonboulangerie/"],
    )
    FAQEntry.objects.create(
        ref="o-que-e-fermentacao-natural",
        question="Pergunta editada no Admin",
        answer="Resposta editada.",
        is_published=False,
    )

    apply_search_presence(shop)
    shop.refresh_from_db()

    assert shop.seo_home_title == "O gestor já escreveu"
    assert shop.seo_home_description.startswith("Padaria artesanal em Londrina")
    assert shop.founding_year == 1997
    assert shop.social_links == [
        "https://wa.me/554333231997",
        "http://instagram.com/nelsonboulangerie/",
        "https://www.facebook.com/nelsonboulangerie",
    ]
    edited = FAQEntry.objects.get(ref="o-que-e-fermentacao-natural")
    assert (edited.question, edited.is_published) == ("Pergunta editada no Admin", False)
    assert FAQEntry.objects.count() == len(PUBLIC_FAQ)
    drafts = set(FAQEntry.objects.filter(is_published=False).values_list("ref", flat=True))
    assert {"posso-cancelar-meu-pedido", "voces-estao-no-ifood"} <= drafts

    assert apply_search_presence(shop) == []


def test_apply_search_presence_without_apply_only_reports(capsys):
    from django.core.management import call_command

    _shop()

    call_command("apply_search_presence")

    assert "rode com --apply" in capsys.readouterr().out
    assert FAQEntry.objects.count() == 0
    assert Shop.objects.get().seo_home_title == ""


def test_initial_faq_never_claims_an_operational_answer_or_breaks_the_house_voice():
    from config.management.commands.apply_search_presence import PUBLIC_FAQ

    _shop()
    for entry in PUBLIC_FAQ:
        FAQEntry(question=entry["question"], answer=entry["answer"], is_published=True).full_clean(exclude=["ref"])
        assert "—" not in entry["answer"], entry["ref"]
        assert "a gente" not in entry["answer"].lower(), entry["ref"]


def test_site_faq_states_the_week_not_the_moment(client):
    _shop()

    hours = next(item for item in _site(client)["faq"] if item["ref"] == "hours")

    assert hours["answer"].startswith("Segunda")
    assert "Aberto" not in hours["answer"] and "Fechado agora" not in hours["answer"]
