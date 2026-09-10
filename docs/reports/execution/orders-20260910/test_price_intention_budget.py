import json, statistics, time, platform
import pytest
from django.db import connection, transaction
from django.test.utils import CaptureQueriesContext
from shopman.offerman.models import Product, Listing, ListingItem
from shopman.shop.models import Channel, Shop
from shopman.backstage.services import catalog
from shopman.shop.services.remote_mutations import run_idempotent_mutation, mutation_fingerprint
pytestmark = pytest.mark.django_db

def test_price_budget():
    Shop.objects.create(name='Price lab')
    listings=[]
    for ref in ('lab-a','lab-b'):
        Channel.objects.create(ref=ref,name=ref,is_active=True)
        listings.append(Listing.objects.create(ref=ref,name=ref,is_active=True))
    observations=[]
    for cells in (10,50,100):
        products=Product.objects.bulk_create([Product(sku=f'PRICE-{cells}-{i}',name=f'Product {i}',unit='un') for i in range(cells//2)])
        ListingItem.objects.bulk_create([ListingItem(product=p,listing=l,price_q=1000) for p in products for l in listings])
        payload={'surface_ref':'*','skus':[p.sku for p in products],'op':'pct','value':10}
        values=[]
        for sample in range(20):
            preview=catalog.preview_bulk_price(payload,actor_id=1)
            body={**payload,'base_revision':preview['base_revision'],'expected_actor_id':1}
            started=time.perf_counter()
            with transaction.atomic():
                with CaptureQueriesContext(connection) as queries:
                    result=run_idempotent_mutation(scope='lab.price-budget',key=f'{cells}-{sample}',fingerprint=mutation_fingerprint(body),execute=lambda:(catalog.apply_bulk_price_intention(body,actor_id=1),200))
                elapsed=(time.perf_counter()-started)*1000
                assert result.response_body['count']==cells
                transaction.set_rollback(True)
            values.append(elapsed)
        observations.append(dict(cells=cells,queries=len(queries),cold_ms=values[0],p50_ms=statistics.median(values),p95_ms=sorted(values)[18]))
    print(json.dumps(dict(platform=platform.platform(),database=connection.vendor,samples=20,remote_adapters=False,observations=observations)))
