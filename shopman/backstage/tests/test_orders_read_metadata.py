"""Read freshness is independent of a live transport connection."""
from datetime import UTC, datetime

import pytest
from django.contrib.auth.models import Permission
from django.urls import reverse
from shopman.orderman.models import Order

from shopman.shop.models import Shop

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize("resource", ["queue", "detail", "catalog", "feeds"])
def test_canonical_reads_include_server_time_and_contract(resource, client, django_user_model, monkeypatch):
    Shop.objects.create(name="Synthetic read metadata")
    user = django_user_model.objects.create_user(username="metadata-reader", is_staff=True)
    user.user_permissions.set(Permission.objects.filter(content_type__app_label="shop", codename__in=["manage_orders", "manage_catalog"]))
    client.force_login(user)
    order = Order.objects.create(ref="READ-METADATA", status="accepted", data={"payment": {"method": "cash"}})
    urls = {"queue": reverse("api-backstage-orders"), "detail": f"/api/v1/backstage/orders/{order.ref}/",
        "catalog": "/api/v1/backstage/catalog/", "feeds": "/api/v1/backstage/feeds/"}
    fixed = datetime(2026, 9, 11, 12, 30, tzinfo=UTC)
    monkeypatch.setattr("shopman.backstage.api.projections.timezone.now", lambda: fixed)
    response = client.get(urls[resource])
    assert response.status_code == 200
    assert response.json()["generated_at"] == fixed.isoformat()
    assert response.json()["contract_version"] == 1
