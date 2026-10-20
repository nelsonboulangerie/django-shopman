"""Vigência por canal: projeção, recorte temporal e custo constante."""

from datetime import date

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from shopman.offerman.models import Listing, ListingItem, Product

from shopman.backstage.projections.catalog import build_catalog_matrix
from shopman.backstage.tests import test_api_catalog_surface as fixtures

catalog = fixtures.catalog
operator = fixtures.operator
shop = fixtures.shop
MATRIX_URL = fixtures.MATRIX_URL
pytestmark = pytest.mark.django_db


def test_validity_query_budget(client, operator, catalog):
    client.force_login(operator)
    params = {"date_from": "2026-10-20", "date_to": "2026-10-20", "order": "validity", "page_size": 10}
    with CaptureQueriesContext(connection) as before:
        small = client.get(MATRIX_URL, params)
    extra = Product.objects.bulk_create(
        [Product(sku=f"VALID{i}", name=f"Produto {i}", base_price_q=100) for i in range(60)]
    )
    web = Listing.objects.get(ref="web")
    ListingItem.objects.bulk_create([ListingItem(product=product, listing=web, price_q=100) for product in extra])
    with CaptureQueriesContext(connection) as after:
        large = client.get(MATRIX_URL, params)
    assert small.status_code == large.status_code == 200
    print(
        f"VALIDITY small={len(before)} large={len(after)} timing_small={small.get('Server-Timing')} timing_large={large.get('Server-Timing')}"
    )
    assert small.json()["matrix"]["total"] == 2
    assert large.json()["matrix"]["total"] == 62
    assert len(large.json()["matrix"]["rows"]) == 10
    assert "projection;dur=" in large["Server-Timing"]
    assert len(before) == len(after)


def test_projects_listing_validity_without_extra_queries(catalog):
    listing = Listing.objects.get(ref="web")
    listing.valid_from, listing.valid_until = date(2026, 10, 20), date(2026, 10, 22)
    listing.save()
    cells = build_catalog_matrix().rows[0].cells
    web = next(cell for cell in cells if cell.surface_ref == "web")
    assert (web.valid_from, web.valid_until) == ("2026-10-20", "2026-10-22")


def test_validity_overlap_inclusive_and_selected_surface(catalog):
    Listing.objects.filter(ref="web").update(valid_from=date(2026, 10, 20), valid_until=date(2026, 10, 22))
    Listing.objects.filter(ref="ifood").update(valid_from=date(2026, 10, 24), valid_until=None)

    def skus(day, refs=None):
        return {
            row.sku for row in build_catalog_matrix(date_from=day, date_to=day, filters={"surface": refs or []}).rows
        }

    assert skus(date(2026, 10, 19)) == set()
    assert skus(date(2026, 10, 20)) == {"PAO", "BOLO"}
    assert skus(date(2026, 10, 22)) == {"PAO", "BOLO"}
    assert skus(date(2026, 10, 23)) == set()
    assert skus(date(2026, 10, 24)) == {"PAO"}
    assert skus(date(2026, 10, 24), ["web"]) == set()


def test_validity_window_cannot_combine_different_listings(catalog):
    Listing.objects.filter(ref="web").update(valid_until=date(2026, 10, 10))
    Listing.objects.filter(ref="ifood").update(valid_from=date(2026, 10, 30))
    out = build_catalog_matrix(date_from=date(2026, 10, 20), date_to=date(2026, 10, 21))
    assert out.total == 0


def test_validity_order_is_chronological_and_stable(catalog):
    Listing.objects.filter(ref="web").update(valid_from=date(2026, 10, 20))
    Listing.objects.filter(ref="ifood").update(valid_from=date(2026, 10, 10))
    # Pão começa no iFood antes do bolo na loja online.
    out = build_catalog_matrix(order="validity", date_from=date(2026, 10, 20), date_to=date(2026, 10, 20))
    assert [row.sku for row in out.rows] == ["PAO", "BOLO"]
    assert out.order == "validity"
    assert out.date_from == out.date_to == "2026-10-20"


@pytest.mark.parametrize(
    "params",
    [
        {"date_from": "ontem"},
        {"date_to": "2026-02-30"},
        {"date_from": "2026-10-22", "date_to": "2026-10-20"},
    ],
)
def test_invalid_period_is_rejected(client, operator, catalog, params):
    client.force_login(operator)
    response = client.get(MATRIX_URL, params)
    assert response.status_code == 400
    assert response.json()["detail"]
    assert response.json()["errors"]
