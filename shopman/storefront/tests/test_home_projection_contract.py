"""Home projection contract guardrails."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.django_db


def test_home_projection_keeps_operational_status_single_sourced(rf):
    from shopman.shop.models import Shop
    from shopman.storefront.api.projections import projection_data
    from shopman.storefront.presentation.home import build_home

    shop = Shop.load() or Shop.objects.create(name="Test Padaria")
    shop.opening_hours = {
        day: {"open": "07:00", "close": "19:00"}
        for day in ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
    }
    shop.save()
    from django.core.cache import cache as django_cache

    from shopman.shop.models.shop import SHOP_CACHE_KEY

    django_cache.delete(SHOP_CACHE_KEY)

    payload = projection_data(build_home(rf.get("/api/v1/storefront/home/")))

    assert {"is_open", "opens_at", "closes_at"}.isdisjoint(payload["omotenashi"])
    assert set(payload["shop_status"]) == {"is_open", "label", "message", "opens_at", "closes_at"}
    assert "notices" in payload
    assert all({"ref", "tone", "title", "message", "priority", "actions"} <= set(notice) for notice in payload["notices"])
    assert payload["shop_status"]["is_open"] in {True, False}
    # Label é copy do registro (`SHOP_STATUS_*`), granular e dependente da HORA:
    # "Aberto até 19h", "Últimos pedidos até 19h" na última hora antes de fechar,
    # "Fechado agora. Abrimos amanhã às 7h".
    #
    # ⚠️ O contrato é "o rótulo é uma das copies DESTE estado", e ele se lê do mesmo
    # registro que a projection usa. Comparar com literal (`startswith("Aberto")`)
    # transformava este teste em bomba-relógio: das 18h às 19h a loja está ABERTA e o
    # rótulo começa com "Últimos pedidos" — e nessa uma hora do dia todo PR do
    # repositório parava num check obrigatório que nada tinha a ver com ele.
    from shopman.storefront.presentation import shop_status as shop_status_copy

    esperadas = (
        ("SHOP_STATUS_OPEN", "SHOP_STATUS_OPEN_UNTIL", "SHOP_STATUS_OPEN_CLOSING_SOON")
        if payload["shop_status"]["is_open"]
        else ("SHOP_STATUS_CLOSED", "SHOP_STATUS_CLOSED_OPENS_AT")
    )
    status_label = payload["shop_status"]["label"]
    assert status_label
    assert any(
        status_label.startswith(shop_status_copy._copy(chave)) for chave in esperadas
    ), status_label


def test_home_projection_does_not_promote_whatsapp_origin_without_cart(rf):
    from shopman.shop.models import Shop
    from shopman.storefront.api.projections import projection_data
    from shopman.storefront.presentation.home import build_home

    Shop.load() or Shop.objects.create(name="Test Padaria")

    request = rf.get("/api/v1/storefront/home/")
    request.session = {"origin_channel": "whatsapp"}

    payload = projection_data(build_home(request))
    notices = {notice["ref"]: notice for notice in payload["notices"]}

    assert "origin_whatsapp" not in notices


def test_home_projection_promotes_whatsapp_origin_only_with_real_cart(rf):
    from shopman.orderman.models import Session

    from shopman.shop.models import Shop
    from shopman.storefront.api.projections import projection_data
    from shopman.storefront.constants import STOREFRONT_CHANNEL_REF
    from shopman.storefront.presentation.home import build_home

    Shop.load() or Shop.objects.create(name="Test Padaria")
    cart = Session.objects.create(
        session_key="home-cart-whatsapp",
        channel_ref=STOREFRONT_CHANNEL_REF,
        state="open",
        items=[{"line_id": "L1", "sku": "PAO-FRANCES", "qty": 1, "unit_price_q": 100}],
    )

    request = rf.get("/api/v1/storefront/home/")
    request.session = {"origin_channel": "whatsapp", "cart_session_key": cart.session_key}

    payload = projection_data(build_home(request))
    notices = {notice["ref"]: notice for notice in payload["notices"]}

    assert notices["origin_whatsapp"]["priority"] == "contextual"
    assert notices["origin_whatsapp"]["tone"] == "info"
    assert notices["origin_whatsapp"]["title"] == "Sua sacola está aqui"
    assert notices["origin_whatsapp"]["actions"][0]["href"] == "/finalizar"
