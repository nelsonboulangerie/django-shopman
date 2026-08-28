"""Start leve do login por WhatsApp (ACCESS-LINK-UNIFICATION).

O ``/start/`` só guarda o contexto do site (sacola anônima + destino) sob um código
``NB-XxXx`` de uso único e devolve o deep link ``wa.me`` já preenchido. Sem
handshake/token/poll/SSE: a identidade é o número que envia a mensagem; o login
acontece depois, pelo access link que o ManyChat devolve (ver ``AccessLinkCreateView``).
As views legado do reverse-OTP (confirm/status/SSE) foram removidas em F4.
"""
from __future__ import annotations

import json
from decimal import Decimal

import pytest
from django.core.cache import cache
from django.test import Client, override_settings
from shopman.doorman.services.link_state import pop_state
from shopman.guestman.models import Customer

from shopman.storefront.tests.api.test_storefront_surface import _seed_surface

pytestmark = pytest.mark.django_db

WA_SETTINGS = {"number": "554333231997", "ttl_seconds": 600}
ACCESS_SETTINGS = {
    "ACCESS_LINK_API_KEY": "test-access-key",
    "ACCESS_LINK_ENTRY_URL": "https://loja.test",
    "CUSTOMER_RESOLVER_CLASS": "shopman.guestman.adapters.auth.CustomerResolver",
}


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear()
    yield
    cache.clear()


def _post_json(client: Client, url: str, data: dict, **extra):
    return client.post(url, data=json.dumps(data), content_type="application/json", **extra)


def _customer() -> Customer:
    return Customer.objects.create(
        ref="CUST-WA",
        first_name="Ana",
        last_name="WhatsApp",
        phone="5543999990001",
    )


def _add_to_cart(client: Client) -> tuple[str, str]:
    product = _seed_surface(stock_qty=Decimal("10"))
    resp = client.put(
        f"/api/v1/cart/skus/{product.sku}/",
        data=json.dumps({"qty": 1}),
        content_type="application/json",
    )
    assert resp.status_code == 200, resp.content
    cart_key = str(client.session.get("cart_session_key") or "")
    assert cart_key
    return product.sku, cart_key


@override_settings(SHOPMAN_WA_VERIFY=WA_SETTINGS)
def test_start_returns_code_and_deep_link(client: Client):
    resp = _post_json(client, "/api/v1/auth/whatsapp/start/", {})
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"].startswith("NB-")
    assert body["message"] == f"#menu {body['code']}"
    assert body["wa_number"] == "554333231997"
    assert body["has_context"] is False
    assert body["has_cart_context"] is False
    assert "wa.me/554333231997" in body["deep_link"]
    assert "%23menu%20" in body["deep_link"]
    # A mensagem inteira vai pré-preenchida; #menu roteia o flow e NB carrega contexto.
    assert body["code"] in body["deep_link"]


@override_settings(SHOPMAN_WA_VERIFY=WA_SETTINGS)
def test_start_stores_cart_and_next_under_code(client: Client):
    # Sacola anônima real + destino → viajam no estado do código (uso único).
    _sku, cart_key = _add_to_cart(client)
    resp = _post_json(client, "/api/v1/auth/whatsapp/start/", {"next": "/checkout"})
    body = resp.json()
    assert body["has_context"] is True
    assert body["has_cart_context"] is True
    assert pop_state(body["code"]) == {"cart_session_key": cart_key, "next": "/checkout"}


@override_settings(SHOPMAN_WA_VERIFY=WA_SETTINGS)
def test_start_without_context_still_issues_code(client: Client):
    resp = _post_json(client, "/api/v1/auth/whatsapp/start/", {})
    body = resp.json()
    assert body["code"].startswith("NB-")
    assert body["has_context"] is False
    assert body["has_cart_context"] is False
    # Estado vazio → o create degrada para o link genérico (sem sacola/destino).
    assert pop_state(body["code"]) == {}


@override_settings(SHOPMAN_WA_VERIFY=WA_SETTINGS)
def test_start_does_not_send_empty_checkout_context(client: Client):
    resp = _post_json(client, "/api/v1/auth/whatsapp/start/", {"next": "/finalizar"})
    body = resp.json()
    assert body["has_context"] is False
    assert pop_state(body["code"]) == {}


@override_settings(SHOPMAN_WA_VERIFY=WA_SETTINGS)
def test_start_ignores_open_redirect_next(client: Client):
    resp = _post_json(
        client, "/api/v1/auth/whatsapp/start/", {"next": "https://evil.example/phish"}
    )
    code = resp.json()["code"]
    # _safe_next descarta destino externo/protocol-relative (guard de open-redirect).
    assert "next" not in (pop_state(code) or {})


@override_settings(SHOPMAN_WA_VERIFY=WA_SETTINGS, DOORMAN=ACCESS_SETTINGS)
def test_full_whatsapp_handoff_preserves_cart_in_new_browser(client: Client):
    customer = _customer()
    sku, cart_key = _add_to_cart(client)

    start = _post_json(client, "/api/v1/auth/whatsapp/start/", {"next": "/finalizar"}).json()
    assert start["has_cart_context"] is True

    create = _post_json(
        Client(),
        "/api/auth/access/create/",
        {
            "customer_id": str(customer.uuid),
            "access_code": start["message"],
            "next": "/menu",
        },
        HTTP_X_API_KEY=ACCESS_SETTINGS["ACCESS_LINK_API_KEY"],
    )
    assert create.status_code == 200, create.content
    link = create.json()
    assert link["has_context"] is True
    assert link["has_cart_context"] is True
    assert link["access_flow"] == "cart_handoff"

    in_app_browser = Client()
    exchange = _post_json(in_app_browser, "/api/v1/auth/access/", {"token": link["token"]})
    assert exchange.status_code == 200, exchange.content
    assert exchange.json()["redirect"] == "/finalizar"
    assert in_app_browser.session.get("cart_session_key") == cart_key

    cart = in_app_browser.get("/api/v1/storefront/cart/").json()["cart"]
    assert cart["items_count"] == 1
    assert cart["items"][0]["sku"] == sku
