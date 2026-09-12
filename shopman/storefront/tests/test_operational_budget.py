import json
import math
import time

import pytest
from django.core.cache import cache
from django.db import connection

from shopman.storefront.tests.api.test_storefront_surface import _seed_surface


@pytest.mark.django_db
def test_local_mutation_budget(client):
    _seed_surface()
    cache.clear()
    times = []
    for n in range(24):
        started = time.perf_counter()
        response = client.put("/api/v1/cart/skus/PAO-FRANCES/", {"qty": 1 + n % 2}, content_type="application/json")
        times.append(1000 * (time.perf_counter() - started))
        assert response.status_code == 200, response.content
        assert response.json()["cart"]["items_count"] == 1 + n % 2
    p95 = sorted(times)[math.ceil(0.95 * len(times)) - 1]
    print(
        "STOREFRONT_LOCAL_BUDGET "
        + json.dumps(
            {
                "samples": len(times),
                "successes": len(times),
                "p95_ms": round(p95, 2),
                "max_ms": round(max(times), 2),
                "budget_ms": 1500,
                "scope": (
                    f"Django test client + {connection.vendor}; "
                    "no browser/network/humans"
                ),
            }
        )
    )
    assert p95 <= 1500
