"""Nome da casa dos apps de operador (GET /api/v1/backstage/operator/tenant/).

Os PWAs de operador se chamam ``"<casa> · <app>"``. O ``<casa>`` é ``Shop.short_name``
e mais nada: o BFF do ``operator-kit`` lê este endpoint sem cookie (o navegador busca o
manifesto sem credencial), então ele tem que responder a anônimo e não pode vazar nada
além do nome que a loja já publica.
"""

from __future__ import annotations

import pytest
from django.core.cache import cache
from django.urls import reverse

from shopman.backstage.projections.operator_tenant import build_operator_tenant
from shopman.shop.models import Shop

URL = "/api/v1/backstage/operator/tenant/"


@pytest.fixture(autouse=True)
def _clear_shop_cache():
    cache.clear()
    yield
    cache.clear()


def test_route_is_the_documented_path():
    assert reverse("api-backstage-operator-tenant") == URL


@pytest.mark.django_db
def test_anonymous_reads_the_shop_short_name(client):
    Shop.objects.create(name="Nelson Boulangerie", brand_name="Nelson Boulangerie", short_name=" Nelson ")

    response = client.get(URL)

    assert response.status_code == 200
    assert response.json() == {"tenant": {"short_name": "Nelson"}}


@pytest.mark.django_db
def test_blank_short_name_does_not_fall_back_to_the_brand(client):
    Shop.objects.create(name="Nelson Boulangerie", brand_name="Nelson Boulangerie", short_name="")

    response = client.get(URL)

    assert response.status_code == 200
    assert response.json() == {"tenant": {"short_name": ""}}


@pytest.mark.django_db
def test_without_shop_answers_empty_instead_of_failing(client):
    response = client.get(URL)

    assert response.status_code == 200
    assert response.json() == {"tenant": {"short_name": ""}}


def test_projection_trims_and_tolerates_missing_shop():
    assert build_operator_tenant(None).short_name == ""
    assert build_operator_tenant(Shop(name="X", short_name="  Nelson ")).short_name == "Nelson"
