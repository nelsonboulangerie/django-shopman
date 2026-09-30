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

from shopman.storefront.api.public_cache import PUBLIC_EDGE_CACHE_CONTROL
from shopman.storefront.services import favorites
from shopman.storefront.tests.api.test_storefront_surface import _seed_surface

pytestmark = pytest.mark.django_db

PUBLIC_TWINS = {
    "/api/v1/storefront/public/home/": "/api/v1/storefront/home/",
    "/api/v1/storefront/public/shell/": "/api/v1/storefront/shell/",
    "/api/v1/storefront/public/catalog/": "/api/v1/storefront/catalog/",
    "/api/v1/storefront/public/catalog/paes/": "/api/v1/storefront/catalog/paes/",
}
PUBLIC_IN_PLACE = ("/api/v1/storefront/site/", "/api/v1/storefront/legal/")


def _customer_client() -> tuple[Client, Customer]:
    """Cliente logado com favorito e sacola: tudo o que a borda não pode espalhar."""
    from shopman.doorman.protocols.customer import AuthCustomerInfo
    from shopman.doorman.services._user_bridge import get_or_create_user_for_customer

    tier, _ = PriceTier.objects.get_or_create(
        ref="regular", defaults={"name": "Regular", "is_default": True, "priority": 0}
    )
    customer = Customer.objects.create(
        ref="CUST-EDGE", first_name="Marisol", phone="+5543999990077", price_tier=tier
    )
    info = AuthCustomerInfo(
        uuid=customer.uuid, name=customer.name, phone=customer.phone, email=None, is_active=True
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
    items = list(catalog.get("items") or [])
    for section in catalog.get("sections") or []:
        items.extend(section.get("items") or [])
    return [bool(item.get("is_favorite")) for item in items]


@pytest.mark.parametrize("path", [*PUBLIC_TWINS, *PUBLIC_IN_PLACE])
def test_public_read_is_edge_cacheable_and_opens_no_session(client, path):
    _seed_surface()

    response = client.get(path)

    assert response.status_code == 200, response.content[:300]
    assert response["Cache-Control"] == PUBLIC_EDGE_CACHE_CONTROL
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
        assert client.get(twin).json() == Client().get(private).json(), twin


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
        "/api/v1/storefront/checkout/",
    ],
)
def test_read_routes_no_longer_hand_out_csrf_cookie(client, path):
    _seed_surface()

    response = client.get(path)

    assert response.status_code == 200
    assert "csrftoken" not in response.cookies
