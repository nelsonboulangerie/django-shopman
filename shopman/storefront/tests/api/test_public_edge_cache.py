"""Cache de borda na leitura pública: estrutura pública sim, estado de sessão nunca.

A Cloudflare ignora ``Vary: Cookie``: resposta ``public`` vai para QUALQUER
requisição da mesma URL. Estes testes provam as duas metades da cerca:

- o que é cacheável não carrega nada de sessão (gêmeas recusam cookie; a
  resposta do anônimo não traz nome, favorito nem sacola de ninguém);
- o que personaliza continua privado, na URL de sempre.
"""

from __future__ import annotations

import json
from decimal import Decimal

import pytest
from django.conf import settings
from django.test import Client
from shopman.guestman.models import Customer, PriceTier

from shopman.storefront.api.public_cache import (
    PUBLIC_EDGE_CACHE_CONTROL,
    RECOMMENDATIONS_EDGE_CACHE_CONTROL,
)
from shopman.storefront.services import favorites
from shopman.storefront.tests.api.test_storefront_surface import _seed_surface

pytestmark = pytest.mark.django_db

# O rail de sugestões é o único request que a PDP faz DEPOIS do SSR, e o corpo do
# anônimo é o mesmo para todo mundo: é ele que mais paga o TTFB do Django.
RECOMMENDATIONS_TWIN = "/api/v1/storefront/public/products/PAO-FRANCES/recommendations/"
RECOMMENDATIONS_PRIVATE = "/api/v1/storefront/products/PAO-FRANCES/recommendations/"
PRODUCT_TWIN = "/api/v1/storefront/public/products/PAO-FRANCES/"
PRODUCT_PRIVATE = "/api/v1/storefront/products/PAO-FRANCES/"

PUBLIC_TWINS = {
    "/api/v1/storefront/public/home/": "/api/v1/storefront/home/",
    "/api/v1/storefront/public/shell/": "/api/v1/storefront/shell/",
    "/api/v1/storefront/public/catalog/": "/api/v1/storefront/catalog/",
    "/api/v1/storefront/public/catalog/paes/": "/api/v1/storefront/catalog/paes/",
    RECOMMENDATIONS_TWIN: RECOMMENDATIONS_PRIVATE,
    PRODUCT_TWIN: PRODUCT_PRIVATE,
}
PUBLIC_IN_PLACE = ("/api/v1/storefront/site/", "/api/v1/storefront/legal/")
# A gêmea do rail tem TTL próprio: a lista muda com o catálogo, não com a venda.
RECOMMENDATIONS_TWINS = (RECOMMENDATIONS_TWIN,)


def _cache_control(path: str) -> str:
    """O TTL é da ROTA: estrutura em 30 s, sugestões da PDP em 60 s."""
    return (
        RECOMMENDATIONS_EDGE_CACHE_CONTROL
        if path in RECOMMENDATIONS_TWINS
        else PUBLIC_EDGE_CACHE_CONTROL
    )


def _customer_client() -> tuple[Client, Customer]:
    """Cliente logado com favorito e sacola: tudo o que a borda não pode espalhar."""
    from shopman.doorman.services._user_bridge import get_or_create_user_for_customer

    from shopman.storefront.tests.identity_fakes import make_identity_view

    tier, _ = PriceTier.objects.get_or_create(
        ref="regular", defaults={"name": "Regular", "is_default": True, "priority": 0}
    )
    customer = Customer.objects.create(
        ref="CUST-EDGE", first_name="Marisol", phone="+5543999990077", price_tiers=tier
    )
    info = make_identity_view(
        subject_id=customer.uuid, name=customer.name, phone=customer.phone, email=None, is_active=True
    )
    user, _ = get_or_create_user_for_customer(info)
    client = Client()
    client.force_login(user, backend="shopman.doorman.backends.PhoneOTPBackend")
    favorites.add(customer.ref, "PAO-FRANCES")
    added = client.put(
        "/api/v1/cart/skus/PAO-FRANCES/",
        data=json.dumps({"qty": 2}),
        content_type="application/json",
    )
    assert added.status_code == 200, added.content[:300]
    return client, customer


def _favorites(body: dict) -> list[bool]:
    catalog = body.get("catalog") or (body.get("home") or {}).get("catalog") or {}
    # A seção carrega só SKUs: todo card do cardápio está em ``items``.
    items = list(catalog.get("items") or [])
    return [bool(item.get("is_favorite")) for item in items]


@pytest.mark.parametrize("path", [*PUBLIC_TWINS, *PUBLIC_IN_PLACE])
def test_public_read_is_edge_cacheable_and_opens_no_session(client, path):
    _seed_surface()

    response = client.get(path)

    assert response.status_code == 200, response.content[:300]
    assert response["Cache-Control"] == _cache_control(path)
    assert not response.cookies, "resposta cacheável não pode definir cookie"


@pytest.mark.parametrize("path", PUBLIC_TWINS)
@pytest.mark.parametrize(
    "credential",
    [
        {"HTTP_COOKIE": "sessionid=qualquer"},
        {"HTTP_COOKIE": "csrftoken=abc"},
        {"HTTP_AUTHORIZATION": "Bearer x"},
        {"QUERY_STRING": "channel=whatsapp"},
    ],
    ids=["session", "csrf", "authorization", "query"],
)
def test_public_twin_refuses_anything_that_could_personalize(client, path, credential):
    _seed_surface()

    response = client.get(path, **credential)

    assert response.status_code == 400
    assert response["Cache-Control"] == "private, no-store"
    assert set(response.json()) <= {"detail", "field", "errors"}


def test_recommendations_twin_serves_the_rail_for_one_minute(client):
    """s-maxage=60 + stale-while-revalidate=60: um minuto de borda, zero de navegador."""
    _seed_surface()

    response = client.get(RECOMMENDATIONS_TWIN)

    assert response.status_code == 200
    assert response["Cache-Control"] == RECOMMENDATIONS_EDGE_CACHE_CONTROL
    assert "max-age=0" in response["Cache-Control"], "quem cacheia é a borda, não o navegador"
    assert "s-maxage=60" in response["Cache-Control"]
    assert "stale-while-revalidate=60" in response["Cache-Control"]


def test_recommendations_twin_does_not_cache_a_missing_product(client):
    """404 não vira resposta pública: cachear o erro esconderia o produto por 1 minuto."""
    _seed_surface()

    response = client.get("/api/v1/storefront/public/products/NAO-EXISTE/recommendations/")

    assert response.status_code == 404
    assert response["Cache-Control"] == "private, no-store"


def test_customer_session_never_reaches_the_cacheable_body():
    """O teste de não-vazamento: cliente com nome, favorito e sacola × anônimo."""
    _seed_surface(stock_qty=Decimal("20"))
    customer_client, customer = _customer_client()
    anonymous = Client()

    private_home = customer_client.get("/api/v1/storefront/home/").json()
    private_shell = customer_client.get("/api/v1/storefront/shell/").json()
    private_catalog = customer_client.get("/api/v1/storefront/catalog/").json()

    # O cenário personaliza de verdade; sem isto o teste seria vazio.
    assert private_shell["shell"]["omotenashi"]["customer_name"] == "Marisol"
    assert private_shell["cart"]["items_count"] == 2
    assert private_home["cart"]["items_count"] == 2
    assert any(_favorites(private_catalog))

    public_home = anonymous.get("/api/v1/storefront/public/home/")
    public_shell = anonymous.get("/api/v1/storefront/public/shell/")
    public_catalog = anonymous.get("/api/v1/storefront/public/catalog/")

    for response, private in (
        (public_home, private_home),
        (public_shell, private_shell),
        (public_catalog, private_catalog),
    ):
        assert response.status_code == 200
        assert response.json() != private
        raw = response.content.decode()
        assert "Marisol" not in raw
        assert customer.phone not in raw
        assert str(customer.uuid) not in raw
        assert customer.ref not in raw

    assert public_shell.json()["shell"]["omotenashi"]["customer_name"] in (None, "")
    assert public_shell.json()["cart"]["items_count"] == 0
    assert public_home.json()["cart"]["items_count"] == 0
    assert not any(_favorites(public_catalog.json()))

    # E o cliente, se bater na gêmea, é recusado: nunca recebe nem deixa corpo público.
    for twin in PUBLIC_TWINS:
        assert customer_client.get(twin).status_code == 400


def test_public_twin_is_the_anonymous_projection_not_a_new_one(client):
    """A gêmea não inventa payload: é o que o anônimo já recebia na rota privada."""
    _seed_surface(stock_qty=Decimal("20"))

    for twin, private in PUBLIC_TWINS.items():
        expected = Client().get(private).json()
        if twin == PRODUCT_TWIN:
            expected.pop("cart")
        assert client.get(twin).json() == expected, twin


@pytest.mark.parametrize("path", PUBLIC_IN_PLACE)
def test_public_in_place_route_ignores_who_is_asking(path):
    """``site/`` e ``legal/`` são públicas na própria URL porque não leem o request."""
    _seed_surface(stock_qty=Decimal("20"))
    customer_client, _ = _customer_client()

    assert customer_client.get(path).json() == Client().get(path).json()


def test_bff_routing_depends_on_the_session_cookie_name():
    """O BFF decide a rota pública pela AUSÊNCIA deste cookie (djangoProxy.ts)."""
    assert settings.SESSION_COOKIE_NAME == "sessionid"


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/storefront/home/",
        "/api/v1/storefront/shell/",
        "/api/v1/storefront/menu/",
        "/api/v1/storefront/catalog/",
        "/api/v1/storefront/products/PAO-FRANCES/",
        "/api/v1/storefront/products/PAO-FRANCES/recommendations/",
        RECOMMENDATIONS_TWIN,
        "/api/v1/storefront/checkout/",
    ],
)
def test_read_routes_no_longer_hand_out_csrf_cookie(client, path):
    _seed_surface()

    response = client.get(path)

    assert response.status_code == 200
    assert "csrftoken" not in response.cookies


def test_public_product_does_not_build_or_include_a_cart(client, monkeypatch):
    from shopman.storefront.api import surface

    _seed_surface(stock_qty=Decimal("20"))

    def unexpected_cart(*args, **kwargs):
        raise AssertionError("a PDP pública tentou montar sacola")

    monkeypatch.setattr(surface, "_cart_payload", unexpected_cart)
    response = client.get(PRODUCT_TWIN)
    assert response.status_code == 200
    assert set(response.json()) == {"product"}
    assert response.json()["product"]["qty_in_cart"] == 0
    assert response.json()["product"]["is_favorite"] is False
    assert response["Cache-Control"] == PUBLIC_EDGE_CACHE_CONTROL


def test_public_product_keeps_personalized_state_in_the_private_path():
    _seed_surface(stock_qty=Decimal("20"))
    customer_client, customer = _customer_client()
    private = customer_client.get(PRODUCT_PRIVATE)
    public = Client().get(PRODUCT_TWIN)
    assert private.status_code == public.status_code == 200
    assert private.json()["product"]["qty_in_cart"] == 2
    assert private.json()["product"]["is_favorite"] is True
    assert private.json()["cart"]["items_count"] == 2
    assert private["Cache-Control"] == "private, no-store"
    assert public.json()["product"]["qty_in_cart"] == 0
    assert public.json()["product"]["is_favorite"] is False
    assert "cart" not in public.json()
    assert customer.ref not in public.content.decode()
    assert customer_client.get(PRODUCT_TWIN).status_code == 400


def test_public_product_does_not_cache_missing_or_unpublished_products(client):
    product = _seed_surface()
    for sku in ("UNKNOWN", product.sku):
        if sku == product.sku:
            product.is_published = False
            product.save(update_fields=["is_published"])
        response = client.get(f"/api/v1/storefront/public/products/{sku}/")
        assert response.status_code == 404
        assert response["Cache-Control"] == "private, no-store"


def test_public_product_head_has_the_same_cache_policy(client):
    _seed_surface()
    response = client.head(PRODUCT_TWIN)
    assert response.status_code == 200
    assert response.content == b""
    assert response["Cache-Control"] == PUBLIC_EDGE_CACHE_CONTROL
    assert not response.cookies
