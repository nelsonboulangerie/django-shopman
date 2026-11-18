"""A primeira adição de quem nunca entrou não cria reserva fantasma (laudo da loja, P2-06).

O defeito: a sessão do Django nascia na primeira escrita. Se o BFF desistia dela
pelo prazo, o Django já tinha reservado, e o ``sessionid`` que nasceu na escrita
se perdia junto com a resposta. A nova tentativa chegava sem sessão, abria outra
sacola e outra reserva: um toque, duas reservas, e a primeira segurando o item.

A correção: a semente do BFF (``seedDjangoSession`` em
``surfaces/storefront-nuxt/server/utils/djangoProxy.ts``) lê a sacola com
``X-Shopman-Session-Seed: 1`` antes da primeira escrita, e essa leitura garante a
sessão. A resposta perdida já não leva o ``sessionid`` embora.
"""
from __future__ import annotations

import json
from decimal import Decimal

import pytest
from django.conf import settings
from shopman.stockman.models import Hold

from shopman.storefront.tests.web.conftest import (
    _ensure_listing_item,
    _seed_stock_for_product_sku,
)

pytestmark = pytest.mark.django_db

SEED = {"HTTP_X_SHOPMAN_SESSION_SEED": "1"}


def _session_cookie(response) -> str:
    morsel = response.cookies.get(settings.SESSION_COOKIE_NAME)
    return morsel.value if morsel is not None else ""


def _set_qty(client, sku: str, qty: int):
    return client.put(
        f"/api/v1/cart/skus/{sku}/",
        data=json.dumps({"qty": qty}),
        content_type="application/json",
    )


def _reserved(sku: str) -> Decimal:
    holds = Hold.objects.filter(sku=sku).active()
    return sum((h.quantity for h in holds), Decimal("0"))


def test_plain_cart_read_creates_no_session(client):
    """Quem só olha a sacola segue anônimo (e servido pela borda no resto da loja)."""
    response = client.get("/api/v1/storefront/cart/")

    assert response.status_code == 200
    assert _session_cookie(response) == ""
    assert response.cookies.get("csrftoken") is not None


def test_seed_read_creates_the_session_with_the_token(client):
    response = client.get("/api/v1/storefront/cart/", **SEED)

    assert response.status_code == 200
    assert _session_cookie(response), "a semente devolve o sessionid antes da primeira escrita"
    assert response.cookies.get("csrftoken") is not None


def test_seed_keeps_an_existing_session(client):
    first = _session_cookie(client.get("/api/v1/storefront/cart/", **SEED))

    again = client.get("/api/v1/storefront/cart/", **SEED)

    assert _session_cookie(again) in ("", first), "semente repetida não troca a sessão"
    assert client.cookies[settings.SESSION_COOKIE_NAME].value == first


def test_lost_first_write_response_does_not_double_the_reservation(client, channel, product):
    """J9 no servidor: a resposta da primeira escrita se perde e o toque é refeito."""
    _seed_stock_for_product_sku(product.sku)
    _ensure_listing_item(channel, product, price_q=90)

    client.get("/api/v1/storefront/cart/", **SEED)
    cookies_after_seed = client.cookies.copy()
    assert cookies_after_seed.get(settings.SESSION_COOKIE_NAME) is not None

    assert _set_qty(client, product.sku, 1).status_code == 200
    # O BFF desistiu pelo prazo: nada da resposta da escrita chega ao navegador.
    client.cookies = cookies_after_seed

    retry = _set_qty(client, product.sku, 1)

    assert retry.status_code == 200, retry.content[:400]
    assert _reserved(product.sku) == Decimal("1"), "um toque, uma reserva"
    cart = client.get("/api/v1/storefront/cart/").json()["cart"]
    assert [(item["sku"], int(item["qty"])) for item in cart["items"]] == [(product.sku, 1)]
