"""Favoritar um esgotado anota o aviso — quando, e só quando, há base para isso.

Decisão do dono (Pablo, 17/09): "Anotado" só aparece quando existe a inscrição
de aviso de verdade; favoritar sozinho não promete aviso. Mas favoritar um
produto esgotado É dizer "quero quando voltar", então:

1. produto notificável (a mesma régua do sino no card) + opt-in de WhatsApp
   verificado + maioridade provada → o favorito cria a inscrição do "Me avise",
   e a resposta devolve o sino para o card virar "Anotado" na hora;
2. sem consentimento ou sem prova de maioridade → só favorito;
3. desfavoritar NÃO cancela o aviso;
4. `conta/favoritos` mostra o esgotado com a mesma pílula do cardápio.

E as regras de engenharia: falha de leitura de consentimento não impede o
favorito (e não cria inscrição); favoritar de novo não duplica; aviso pausado ou
cancelado pelo cliente não é retomado pelo favorito.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.test import Client
from shopman.guestman.models import Customer
from shopman.offerman.models import Product

from shopman.shop.models import Channel
from shopman.shop.services import account as account_service
from shopman.shop.services.marketing_age import ADULT_DECLARATION_KEY
from shopman.storefront.models import CustomerFavorite, StockAlertSubscription
from shopman.storefront.services import favorites, stock_alerts

from .test_auth_session import _csrf_headers, _login_as_customer

pytestmark = pytest.mark.django_db

SKU = "FAV-ALERT-PAO"
URL = f"/api/v1/account/favorites/{SKU}/"

SOLD_OUT = {"availability_policy": "planned_ok", "total_promisable": Decimal("0"), "is_planned": False}
AVAILABLE = {"availability_policy": "planned_ok", "total_promisable": Decimal("50"), "is_planned": False}
PAUSED = {"is_paused": True}


@pytest.fixture(autouse=True)
def _disable_request_rate_limits(settings):
    settings.RATELIMIT_ENABLE = False


@pytest.fixture(autouse=True)
def _storefront_channel():
    Channel.objects.get_or_create(ref="web", defaults={"name": "Loja Online"})


@pytest.fixture
def product():
    return Product.objects.create(
        sku=SKU, name="Pão de Fermentação", base_price_q=1800, is_published=True, is_sellable=True
    )


def _customer(*, adult: bool = True, opted_in: bool = True, birthday: date | None = None) -> Customer:
    metadata = {}
    if adult:
        metadata[ADULT_DECLARATION_KEY] = {
            "at": "2026-09-16T10:00:00-03:00",
            "terms_version": account_service.LOGIN_TERMS_VERSION,
            "source": "storefront_login",
        }
    customer = Customer.objects.create(
        ref="CUS-FAV-ALERT",
        first_name="Ana",
        phone="+5543999992001",
        birthday=birthday,
        metadata=metadata,
    )
    if opted_in:
        account_service.answer_marketing_prompt(
            customer.ref,
            whatsapp=True,
            disclosure_text="Quero receber novidades pelo WhatsApp.",
            disclosure_version="test-v1",
        )
    return customer


def _availability(raw):
    return patch(
        "shopman.storefront.presentation.catalog._batch_availability",
        side_effect=lambda skus, channel_ref: dict.fromkeys(skus, raw),
    )


def _favorite(client: Client, raw=SOLD_OUT):
    with _availability(raw):
        return client.post(URL, **_csrf_headers(client))


def _subscriptions(customer: Customer):
    return StockAlertSubscription.objects.filter(customer_ref=customer.ref, sku=SKU)


def _warned(mock_logger) -> str:
    # Os loggers `shopman.*` não propagam para o caplog; lê a chamada direto.
    return " ".join(str(call.args[0]) for call in mock_logger.warning.call_args_list)


def _is_favorite(customer: Customer) -> bool:
    return CustomerFavorite.objects.filter(customer_ref=customer.ref, sku=SKU).exists()


# ── 1. esgotado + opt-in + maioridade → anota ──────────────────────────


def test_sold_out_favorite_with_opt_in_and_adulthood_notes_the_alert(client: Client, product):
    customer = _customer()
    _login_as_customer(client, customer)

    response = _favorite(client)

    assert response.status_code == 200
    body = response.json()
    assert body["is_favorite"] is True
    assert body["is_notify_subscribed"] is True
    assert body["stock_alert_noted"] is True
    assert _is_favorite(customer)
    sub = _subscriptions(customer).get()
    assert sub.is_active
    assert sub.purpose == "stock_availability"
    assert sub.delivery_channel == "whatsapp"
    # A base registrada é o que de fato autorizou — não o texto do "Me avise",
    # que a pessoa não leu neste gesto.
    assert sub.disclosure_version == favorites.FAVORITE_STOCK_ALERT_BASIS_VERSION
    assert sub.disclosure_text == favorites.FAVORITE_STOCK_ALERT_BASIS
    assert sub.adult_declared is True
    assert sub.proof_status == "verified"


def test_the_favorites_page_shows_the_bell_as_noted(client: Client, product):
    """Regra 4: a página de favoritos traz o esgotado com a pílula do cardápio."""
    customer = _customer()
    _login_as_customer(client, customer)
    _favorite(client)

    with _availability(SOLD_OUT):
        response = client.get("/api/v1/account/favorites/")

    assert response.status_code == 200
    [item] = response.json()["items"]
    assert item["sku"] == SKU
    assert item["availability"] == "unavailable"
    assert item["is_notifiable"] is True
    assert item["is_notify_subscribed"] is True


def test_the_favorites_page_offers_me_avise_when_nothing_was_noted(client: Client, product):
    customer = _customer(opted_in=False)
    _login_as_customer(client, customer)
    _favorite(client)

    with _availability(SOLD_OUT):
        [item] = client.get("/api/v1/account/favorites/").json()["items"]

    assert item["is_notifiable"] is True
    assert item["is_notify_subscribed"] is False


# ── 2. sem base → só favorito ──────────────────────────────────────────


def test_without_whatsapp_opt_in_it_is_only_a_favorite(client: Client, product):
    customer = _customer(opted_in=False)
    _login_as_customer(client, customer)

    body = _favorite(client).json()

    assert body["is_favorite"] is True
    assert body["is_notify_subscribed"] is False
    assert body["stock_alert_noted"] is False
    assert _is_favorite(customer)
    assert not _subscriptions(customer).exists()


def test_opted_out_customer_is_only_a_favorite(client: Client, product):
    from shopman.guestman import ConsentService

    customer = _customer()
    ConsentService.revoke_consent(customer.ref, "whatsapp")
    _login_as_customer(client, customer)

    body = _favorite(client).json()

    assert body["stock_alert_noted"] is False
    assert not _subscriptions(customer).exists()


def test_without_proof_of_adulthood_it_is_only_a_favorite(client: Client, product):
    customer = _customer(adult=False)
    _login_as_customer(client, customer)

    body = _favorite(client).json()

    assert body["is_favorite"] is True
    assert body["stock_alert_noted"] is False
    assert _is_favorite(customer)
    assert not _subscriptions(customer).exists()


def test_a_birthday_that_proves_a_minor_vetoes_the_declaration(client: Client, product):
    today = date.today()
    customer = _customer(birthday=date(today.year - 15, 1, 1))
    _login_as_customer(client, customer)

    body = _favorite(client).json()

    assert body["stock_alert_noted"] is False
    assert not _subscriptions(customer).exists()


def test_available_product_is_only_a_favorite(client: Client, product):
    customer = _customer()
    _login_as_customer(client, customer)

    body = _favorite(client, AVAILABLE).json()

    assert body["is_favorite"] is True
    assert body["is_notify_subscribed"] is False
    assert body["stock_alert_noted"] is False
    assert not _subscriptions(customer).exists()


def test_paused_product_is_only_a_favorite(client: Client, product):
    """Pausa é decisão do operador, não falta: o card não oferece sino."""
    customer = _customer()
    _login_as_customer(client, customer)

    body = _favorite(client, PAUSED).json()

    assert body["stock_alert_noted"] is False
    assert not _subscriptions(customer).exists()


def test_product_paused_only_in_the_storefront_listing_is_only_a_favorite(client: Client, product):
    customer = _customer()
    _login_as_customer(client, customer)

    with patch(
        "shopman.shop.projections.catalog_context.listing_sellable_map",
        return_value={SKU: False},
    ):
        body = _favorite(client).json()

    assert body["stock_alert_noted"] is False
    assert not _subscriptions(customer).exists()


# ── 3. desfavoritar não cancela; idempotência; escolha do cliente ─────


def test_unfavoriting_keeps_the_alert(client: Client, product):
    customer = _customer()
    _login_as_customer(client, customer)
    _favorite(client)

    response = client.delete(URL, **_csrf_headers(client))

    assert response.status_code == 200
    body = response.json()
    assert body["is_favorite"] is False
    assert body["is_notify_subscribed"] is True
    assert not _is_favorite(customer)
    assert _subscriptions(customer).get().is_active


def test_favoriting_again_does_not_duplicate_the_alert(client: Client, product):
    customer = _customer()
    _login_as_customer(client, customer)

    _favorite(client)
    second = _favorite(client).json()
    client.delete(URL, **_csrf_headers(client))
    third = _favorite(client).json()

    assert second["is_notify_subscribed"] is True
    assert second["stock_alert_noted"] is False
    assert third["is_notify_subscribed"] is True
    assert third["stock_alert_noted"] is False
    assert _subscriptions(customer).count() == 1
    assert CustomerFavorite.objects.filter(customer_ref=customer.ref, sku=SKU).count() == 1


def test_an_alert_the_customer_cancelled_is_not_recreated(client: Client, product):
    customer = _customer()
    _login_as_customer(client, customer)
    _favorite(client)
    sub = _subscriptions(customer).get()
    assert stock_alerts.revoke(sub.ref, sku=SKU, customer=customer) is True
    client.delete(URL, **_csrf_headers(client))

    body = _favorite(client).json()

    assert body["is_favorite"] is True
    assert body["is_notify_subscribed"] is False
    assert body["stock_alert_noted"] is False
    assert _subscriptions(customer).count() == 1
    assert _subscriptions(customer).get().revoked_at is not None


def test_an_alert_the_customer_paused_is_not_resumed(client: Client, product):
    customer = _customer()
    _login_as_customer(client, customer)
    _favorite(client)
    sub = _subscriptions(customer).get()
    assert stock_alerts.set_paused(sub.ref, paused=True, sku=SKU, customer=customer) is True
    client.delete(URL, **_csrf_headers(client))

    body = _favorite(client).json()

    assert body["is_notify_subscribed"] is False
    assert body["stock_alert_noted"] is False
    sub.refresh_from_db()
    assert sub.paused_at is not None
    assert _subscriptions(customer).count() == 1


def test_an_alert_created_by_me_avise_is_kept_as_is(client: Client, product):
    customer = _customer()
    _login_as_customer(client, customer)
    existing = stock_alerts.subscribe(SKU, customer=customer, adult_declared=True)
    assert existing is not None

    body = _favorite(client).json()

    assert body["is_notify_subscribed"] is True
    assert body["stock_alert_noted"] is False
    assert list(_subscriptions(customer)) == [existing]


# ── falhar fechado: o favorito nunca quebra por causa do aviso ─────────


def test_consent_read_failure_saves_the_favorite_without_an_alert(client: Client, product):
    customer = _customer()
    _login_as_customer(client, customer)

    with (
        patch(
            "shopman.guestman.ConsentService.get_customer_statuses",
            side_effect=RuntimeError("consent store down"),
        ),
        patch("shopman.shop.services.communication_consent.logger") as log,
    ):
        response = _favorite(client)

    assert response.status_code == 200
    body = response.json()
    assert body["is_favorite"] is True
    assert body["stock_alert_noted"] is False
    assert _is_favorite(customer)
    assert not _subscriptions(customer).exists()
    assert "reason=opt_in_unreadable" in _warned(log)


def test_availability_read_failure_saves_the_favorite_without_an_alert(client: Client, product):
    customer = _customer()
    _login_as_customer(client, customer)

    with (
        patch(
            "shopman.storefront.presentation.catalog._batch_availability",
            side_effect=RuntimeError("stock down"),
        ),
        patch("shopman.storefront.services.favorites.logger") as log,
    ):
        response = client.post(URL, **_csrf_headers(client))

    assert response.status_code == 200
    assert response.json()["stock_alert_noted"] is False
    assert _is_favorite(customer)
    assert not _subscriptions(customer).exists()
    assert "reason=availability_unreadable" in _warned(log)


def test_subscribe_failure_saves_the_favorite_without_an_alert(client: Client, product):
    customer = _customer()
    _login_as_customer(client, customer)

    with (
        patch(
            "shopman.storefront.services.stock_alerts.subscribe_with_outcome",
            side_effect=RuntimeError("boom"),
        ),
        patch("shopman.storefront.services.favorites.logger") as log,
    ):
        response = _favorite(client)

    assert response.status_code == 200
    assert response.json()["stock_alert_noted"] is False
    assert _is_favorite(customer)
    assert not _subscriptions(customer).exists()
    assert "reason=subscribe_failed" in _warned(log)
