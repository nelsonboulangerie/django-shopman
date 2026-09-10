import json, platform, statistics, time
import pytest
from django.test.utils import CaptureQueriesContext
from django.db import connection, reset_queries
from shopman.orderman.models import Order
from shopman.shop.models import Shop
from shopman.backstage.projections.order_queue import build_order_queue, build_two_zone_queue
from shopman.backstage.api.projections import projection_data
pytestmark=pytest.mark.django_db

def test_read_baseline():
    Shop.objects.create(name="Orders lab")
    observations=[]
    for n in (1,10,100,500):
        Order.objects.all().delete()
        Order.objects.bulk_create([Order(ref=f"LAB-{n}-{i}", channel_ref="web",status="ready",total_q=1500,data={"fulfillment_type":"pickup","payment":{"method":"cash"}}) for i in range(n)])
        for build in (build_order_queue,build_two_zone_queue):
            elapsed=[]
            for sample in range(20):
                reset_queries()
                start=time.perf_counter()
                with CaptureQueriesContext(connection) as queries:
                    result=projection_data(build())
                elapsed.append((time.perf_counter()-start)*1000)
            observations.append(dict(n=n,projection=build.__name__,queries=len(queries),holds=sum("stockman_hold" in q["sql"].lower() for q in queries),bytes=len(json.dumps(result).encode()),cold_ms=elapsed[0],p50_ms=statistics.median(elapsed),p95_ms=sorted(elapsed)[18]))
    print(json.dumps(dict(platform=platform.platform(),database=connection.vendor,samples=20,observations=observations)))
