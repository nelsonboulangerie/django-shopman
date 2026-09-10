"""Synthetic local-write baseline; adapters replaced, never remote sync."""
import json, statistics, time
from unittest.mock import patch
import pytest
from django.db import connection, transaction, reset_queries
from django.test.utils import CaptureQueriesContext
from shopman.offerman.models import Product, Listing, ListingItem
from shopman.shop.models import Shop, Channel
from shopman.backstage.services import catalog

pytestmark = pytest.mark.django_db

def test_local_cell_budget():
    Shop.objects.create(name="Orders lab")
    Channel.objects.create(ref="lab", name="Lab")
    listing = Listing.objects.create(ref="lab", name="Lab")
    products = Product.objects.bulk_create([Product(sku=f"LAB-{i}", name=f"Lab {i}", unit="un", base_price_q=1000) for i in range(1000)])
    ListingItem.objects.bulk_create([ListingItem(product=p,listing=listing,price_q=1000) for p in products])
    results=[]
    for n in (10,100,500,1000):
        times=[]
        skus=[p.sku for p in products[:n]]
        for _ in range(20):
            reset_queries()
            with patch.object(catalog, "_reconcile_if_projected"), patch.object(catalog, "_notify_surface"):
                start=time.perf_counter()
                with CaptureQueriesContext(connection) as queries:
                    with transaction.atomic():
                        assert catalog.bulk_price(skus,"lab",op="pct",value=10)==n
                        transaction.set_rollback(True)
                times.append((time.perf_counter()-start)*1000)
        results.append(dict(cells=n,p50_ms=statistics.median(times),p95_ms=sorted(times)[18],queries=len(queries)))
    assert ListingItem.objects.filter(price_q=1000).count()==1000
    print(json.dumps(dict(database=connection.vendor,samples=20,rollback_each_sample=True,sync="mock",measurements=results)))
