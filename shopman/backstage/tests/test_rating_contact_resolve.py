"""Ouvidoria no Gestor: o caso aparece no pedido e só fecha no "Resolvido", com nota."""

from __future__ import annotations

import pytest
from django.contrib.auth.models import Permission, User
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse
from django.utils import timezone
from shopman.orderman.models import Order

from shopman.backstage.models import OperatorAlert
from shopman.backstage.projections.alerts import alert_context_href
from shopman.backstage.projections.order_queue import build_operator_order
from shopman.shop.services import customer_contact

pytestmark = [pytest.mark.django_db, pytest.mark.channels("web")]


@pytest.fixture
def operator(db):
    perm = Permission.objects.get(
        content_type=ContentType.objects.get(app_label="shop", model="shop"), codename="manage_orders",
    )
    user = User.objects.create_user("ouvidoria-op", password="pw", is_staff=True)
    user.user_permissions.add(perm)
    return user


def _rated(rating: int, comment: str = "") -> Order:
    return Order.objects.create(
        ref=f"NB-OUV-{rating}",
        channel_ref="web",
        status="delivered",
        total_q=2000,
        handle_type="phone",
        handle_ref="+5543999990001",
        data={
            "customer_rating": {
                "rating": rating,
                "comment": comment,
                "submitted_at": timezone.now().isoformat(),
                "source": "storefront_nuxt",
            },
        },
    )


def _url(order: Order) -> str:
    return reverse("api-backstage-order-customer-contact-resolve", args=[order.ref])


def test_open_request_shows_on_the_order_and_alert_points_to_it():
    order = _rated(2, "Demorou demais")
    customer_contact.request_contact(order)

    projection = build_operator_order(order)

    assert projection.contact_request is not None
    assert projection.contact_request.rating == 2
    assert projection.contact_request.comment == "Demorou demais"
    alert = OperatorAlert.objects.get(type="customer_contact_requested", order_ref=order.ref)
    href, label = alert_context_href(alert, surface="orders")
    assert href == f"/{order.ref}#customer-contact"
    assert label == "Falar com o cliente"


def test_resolve_needs_a_note(client, operator):
    order = _rated(3)
    customer_contact.request_contact(order)
    client.force_login(operator)

    response = client.post(_url(order), data={"note": "  "}, content_type="application/json")

    assert response.status_code == 400
    assert response.json()["field"] == "note"
    assert customer_contact.open_request(order) is not None


def test_resolve_closes_the_case_and_the_alert(client, operator):
    order = _rated(1, "Chegou frio")
    customer_contact.request_contact(order)
    client.force_login(operator)

    response = client.post(
        _url(order),
        data={"note": "Liguei, pedi desculpas e combinamos a troca."},
        content_type="application/json",
    )

    assert response.status_code == 200, response.content
    assert customer_contact.open_request(order) is None
    assert build_operator_order(order).contact_request is None
    event = order.events.get(type=customer_contact.RESOLVED_EVENT)
    assert event.payload == {"note": "Liguei, pedi desculpas e combinamos a troca."}
    assert not OperatorAlert.objects.filter(
        type="customer_contact_requested", order_ref=order.ref, resolved_at__isnull=True,
    ).exists()

    # Já fechado: não há o que resolver de novo.
    again = client.post(_url(order), data={"note": "de novo"}, content_type="application/json")
    assert again.status_code == 409


def test_resolve_needs_who_manages_orders(client):
    order = _rated(2)
    customer_contact.request_contact(order)
    user = User.objects.create_user("sem-perm", password="pw", is_staff=True)
    client.force_login(user)

    assert client.post(_url(order), data={"note": "ok"}, content_type="application/json").status_code == 403
