"""Orçamento de consultas da sacola: o custo não cresce com o número de itens.

Com sacola, ``home/``, ``menu/`` e ``shell/`` faziam ~120 a ~150 consultas a
mais que sem ela (medido no seed, 30/09), e quase tudo por item ou por produto:

- ``keywords.names()`` no motor de sugestão — no django-taggit 6.1 é um
  ``values_list`` que ignora o ``prefetch_related("keywords")``: uma consulta
  por produto do pool e da sacola;
- uma consulta de ``Hold`` por linha para saber se ela está em fila;
- três leituras de ``Product`` para os mesmos SKUs, e os produtos da sacola
  lidos duas vezes pelo motor de sugestão.

Este arquivo trava o que ficou: a sacola com 1 item e com 5 itens fazem o MESMO
número de consultas, e há um teto absoluto para a sacola e para o que ela
acrescenta a ``menu/`` e ``home/``.

⚠️ O estoque aqui é todo de HOJE de propósito. A disponibilidade com fornada
futura (``waitlist.next_batch_availability_for_skus``) ainda faz uma leitura por
DATA de fornada distinta; ela é do caminho do catálogo, não da sacola, e tem
frente própria.
"""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal

import pytest
from django.db import connection
from django.test import Client, RequestFactory
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from shopman.offerman.models import Collection, CollectionItem, ListingItem, Product

from shopman.shop.models import Channel, ProductAffinity
from shopman.storefront.constants import STOREFRONT_CHANNEL_REF
from shopman.storefront.presentation import build_cart

pytestmark = pytest.mark.django_db

PAES = [f"PAO-{i}" for i in range(1, 6)]
BEBIDAS = ["CAFE", "SUCO", "CHA"]

#: Tetos absolutos. Medidos neste arquivo em 30/09/2026: a sacola faz 44
#: consultas (eram 62 com 1 item e 70 com 5) e acrescenta 47 a ``menu/`` e
#: ``home/`` (eram 65 com 1 item e 73 com 5). A folga é para mudança honesta;
#: estourar quer dizer que voltou a haver leitura por item ou por produto —
#: procure o laço antes de subir o número.
CART_PROJECTION_CEILING = 50
CART_OVERHEAD_CEILING = 53


@pytest.fixture
def catalog(listing):
    from shopman.stockman import stock
    from shopman.stockman.models import Position, PositionKind

    Channel.objects.get_or_create(ref=STOREFRONT_CHANNEL_REF, defaults={"name": "Loja Online"})
    position, _ = Position.objects.get_or_create(
        ref="loja",
        defaults={"name": "Loja", "kind": PositionKind.PHYSICAL, "is_saleable": True},
    )
    paes = Collection.objects.create(ref="paes", name="Pães", is_active=True, sort_order=1)
    bebidas = Collection.objects.create(ref="bebidas", name="Bebidas", is_active=True, sort_order=2)

    for index, sku in enumerate(PAES + BEBIDAS):
        is_bebida = sku in BEBIDAS
        product = Product.objects.create(
            sku=sku,
            name=sku.title(),
            base_price_q=500 + index * 100,
            is_published=True,
            is_sellable=True,
            availability_policy="demand_ok" if is_bebida else "planned_ok",
        )
        product.keywords.add("bebida" if is_bebida else "pao", f"tag-{index}")
        CollectionItem.objects.create(
            collection=bebidas if is_bebida else paes, product=product, sort_order=index,
        )
        ListingItem.objects.create(
            listing=listing, product=product, price_q=product.base_price_q,
            is_published=True, is_sellable=True,
        )
        if not is_bebida:
            stock.receive(
                quantity=Decimal("50"), sku=sku, position=position,
                target_date=date.today(), reason="orçamento da sacola",
            )

    # O histórico liga cada pão às bebidas: é o que põe o trilho de sugestão
    # para trabalhar inteiro (candidatos, portões, pontuação) nas duas sacolas.
    for pao in PAES:
        for bebida in BEBIDAS:
            ProductAffinity.objects.create(
                sku_a=pao, sku_b=bebida, together_count=10, score=10.0,
                lift=2.0, window_days=365, computed_at=timezone.now(),
            )


def _client_with_cart(skus: list[str]) -> Client:
    client = Client()
    for sku in skus:
        response = client.put(
            f"/api/v1/cart/skus/{sku}/",
            data=json.dumps({"qty": 1}),
            content_type="application/json",
        )
        assert response.status_code in (200, 201), (sku, response.status_code, response.content[:300])
    return client


def _cart_queries(client: Client) -> tuple[int, object]:
    request = RequestFactory().get("/sacola/")
    request.session = client.session  # type: ignore[attr-defined]
    build_cart(request=request, channel_ref=STOREFRONT_CHANNEL_REF)  # aquece caches do processo
    with CaptureQueriesContext(connection) as ctx:
        projection = build_cart(request=request, channel_ref=STOREFRONT_CHANNEL_REF)
    return len(ctx.captured_queries), projection


def _endpoint_queries(client: Client, path: str) -> int:
    client.get(path)  # aquece caches do processo
    with CaptureQueriesContext(connection) as ctx:
        response = client.get(path)
    assert response.status_code == 200, (path, response.status_code)
    return len(ctx.captured_queries)


def test_cart_projection_costs_the_same_with_one_or_five_items(catalog):
    one, one_projection = _cart_queries(_client_with_cart(PAES[:1]))
    five, five_projection = _cart_queries(_client_with_cart(PAES))

    assert len(one_projection.items) == 1
    assert len(five_projection.items) == 5
    # O trilho de sugestão rodou nas duas: sem ele o teste mediria a sacola sem
    # a parte que mais custava.
    assert one_projection.upsell is not None
    assert five_projection.upsell is not None

    assert five == one, f"sacola com 5 itens fez {five} consultas; com 1 item, {one}"
    assert one <= CART_PROJECTION_CEILING, f"sacola fez {one} consultas (teto {CART_PROJECTION_CEILING})"


@pytest.mark.parametrize("path", ["/api/v1/storefront/menu/", "/api/v1/storefront/home/"])
def test_cart_adds_a_bounded_cost_to_menu_and_home(catalog, path):
    without_cart = _endpoint_queries(Client(), path)
    with_one = _endpoint_queries(_client_with_cart(PAES[:1]), path)
    with_five = _endpoint_queries(_client_with_cart(PAES), path)

    assert with_five == with_one, f"{path}: 5 itens fizeram {with_five} consultas; 1 item, {with_one}"
    overhead = with_one - without_cart
    assert overhead <= CART_OVERHEAD_CEILING, (
        f"{path}: a sacola acrescentou {overhead} consultas (teto {CART_OVERHEAD_CEILING})"
    )
