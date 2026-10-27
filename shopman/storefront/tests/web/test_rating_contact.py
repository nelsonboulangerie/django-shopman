"""Depois de avaliar: ouvidoria para nota até 3, convite do Google para toda nota.

A política do Google proíbe convidar só quem gostou (decisão do dono, 27/10/2026):
quem não gostou vê primeiro a oferta de contato, e o convite continua lá.
"""

from __future__ import annotations

import json

import pytest
from shopman.orderman.models import OrderEvent

from shopman.backstage.models import OperatorAlert
from shopman.shop.models import Shop
from shopman.shop.services import customer_contact

pytestmark = pytest.mark.django_db


@pytest.fixture
def shop_with_place(db):
    shop = Shop.load() or Shop.objects.create(name="Loja")
    shop.place_id = "ChIJ-casa"
    shop.save()
    return shop


def _rate(client, ref: str, rating: int, comment: str = ""):
    return client.post(
        f"/api/v1/orders/{ref}/rate/",
        data=json.dumps({"rating": rating, "comment": comment}),
        content_type="application/json",
        HTTP_X_IDEMPOTENCY_KEY=f"rate-{rating}",
    )


def _ask_contact(client, ref: str, *, key: str = "contact-1"):
    return client.post(
        f"/api/v1/orders/{ref}/contact-request/",
        data=json.dumps({}),
        content_type="application/json",
        HTTP_X_IDEMPOTENCY_KEY=key,
    )


@pytest.fixture
def delivered(order):
    # Atalho de teste: o pedido entregue sem percorrer o ciclo (só a avaliação importa).
    type(order).objects.filter(pk=order.pk).update(status="delivered")
    order.refresh_from_db()
    return order


def test_unrated_order_has_no_followup(delivered):
    from shopman.storefront.presentation.order_tracking import build_order_tracking

    projection = build_order_tracking(delivered)

    assert projection.rating_followup is None
    assert not any(action.ref == "request_contact" for action in projection.actions)


def test_low_rating_offers_contact_and_google_invite(client, delivered, shop_with_place):
    response = _rate(client, delivered.ref, 3, "Pão veio amassado")

    assert response.status_code == 200
    payload = response.json()
    followup = payload["rating_followup"]
    assert followup["contact_offered"] is True
    assert followup["contact_requested"] is False
    assert followup["comment"] == "Pão veio amassado"
    assert followup["google_review_url"] == (
        "https://search.google.com/local/writereview?placeid=ChIJ-casa"
    )
    action = next(a for a in payload["actions"] if a["ref"] == "request_contact")
    assert action["href"] == f"/api/v1/orders/{delivered.ref}/contact-request/"


def test_good_rating_gets_the_same_google_invite_and_no_contact(client, delivered, shop_with_place):
    payload = _rate(client, delivered.ref, 5, "Perfeito").json()

    followup = payload["rating_followup"]
    assert followup["contact_offered"] is False
    assert followup["google_review_url"].endswith("placeid=ChIJ-casa")
    assert not any(a["ref"] == "request_contact" for a in payload["actions"])


def test_without_place_id_there_is_no_google_invite(client, delivered):
    shop = Shop.load()
    if shop is not None:
        shop.place_id = ""
        shop.save()

    followup = _rate(client, delivered.ref, 2).json()["rating_followup"]

    assert followup["google_review_url"] == ""
    assert followup["contact_offered"] is True


def test_contact_request_routes_to_orders_once(client, delivered, shop_with_place):
    _rate(client, delivered.ref, 1, "Chegou frio")

    response = _ask_contact(client, delivered.ref)

    assert response.status_code == 200
    followup = response.json()["rating_followup"]
    assert followup["contact_requested"] is True
    assert followup["contact_offered"] is False
    event = OrderEvent.objects.get(order=delivered, type=customer_contact.REQUESTED_EVENT)
    # Só a nota: o comentário mora na avaliação, de onde a exclusão de conta o apaga.
    assert event.payload == {"rating": 1}
    alert = OperatorAlert.objects.get(type="customer_contact_requested", order_ref=delivered.ref)
    assert alert.audience == "orders"
    assert "nota 1/5" in alert.message
    assert "Chegou frio" not in alert.message

    # De novo (outra chave): devolve o caso que existe, sem abrir outro.
    assert _ask_contact(client, delivered.ref, key="contact-2").status_code == 200
    assert OrderEvent.objects.filter(order=delivered, type=customer_contact.REQUESTED_EVENT).count() == 1
    assert OperatorAlert.objects.filter(type="customer_contact_requested", order_ref=delivered.ref).count() == 1


def test_contact_request_is_refused_for_a_good_rating(client, delivered):
    _rate(client, delivered.ref, 4)

    response = _ask_contact(client, delivered.ref)

    assert response.status_code == 409
    assert response.json()["error_code"] == "contact_request_not_applicable"
    assert not OperatorAlert.objects.filter(type="customer_contact_requested").exists()


def test_contact_request_needs_access_to_the_order(delivered):
    from django.test import Client

    _rate_anyone = Client()
    response = _ask_contact(_rate_anyone, delivered.ref)

    assert response.status_code == 404
